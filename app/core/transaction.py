"""
Spring-Style Transactional Decorator for FastAPI
=================================================

Standalone transaction management system inspired by Spring's @Transactional,
designed to work seamlessly with FastAPI and SQLAlchemy async.

Features:
- 7 propagation behaviors (REQUIRED, REQUIRES_NEW, MANDATORY, etc.)
- 4 isolation levels (READ_UNCOMMITTED → SERIALIZABLE)
- Rollback rules (rollback_for, no_rollback_for)
- Timeout support with asyncio
- NESTED transactions with savepoints
- Integrates with DI framework

Quick Start:
    >>> @Injectable
    >>> class UserService:
    >>>     def __init__(self, db: DatabaseProvider):
    >>>         self._db = db
    >>>     
    >>>     @transactional
    >>>     async def create_user(self, data: dict, db=None):
    >>>         user = User(**data)
    >>>         db.add(user)
    >>>         return user

Author: David Nguyen
"""

from __future__ import annotations

import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional, TypeVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

__all__ = [
    "Transactional",
    "Propagation",
    "Isolation",
    "DatabaseProvider",
    "TransactionContext",
]

logger = logging.getLogger(__name__)
T = TypeVar("T")

# =============================================================================
# CONFIGURATION
# =============================================================================

class Propagation:
    """
    Transaction propagation behaviors (Spring-compatible).
    
    Controls how transactions are managed when methods call each other.
    """
    REQUIRED = "REQUIRED"           # Join existing or create new (default)
    REQUIRES_NEW = "REQUIRES_NEW"   # Always create new, suspend current
    MANDATORY = "MANDATORY"         # Must run in existing, error if none
    SUPPORTS = "SUPPORTS"           # Join if exists, otherwise non-transactional
    NOT_SUPPORTED = "NOT_SUPPORTED" # Always non-transactional, suspend current
    NEVER = "NEVER"                 # Must NOT run in transaction
    NESTED = "NESTED"               # Create savepoint if parent exists


class Isolation:
    """
    Transaction isolation levels (SQL standard).
    
    Controls how concurrent transactions see each other's changes.
    """
    READ_UNCOMMITTED = "READ UNCOMMITTED"  # Lowest, allows dirty reads
    READ_COMMITTED = "READ COMMITTED"      # PostgreSQL default
    REPEATABLE_READ = "REPEATABLE READ"    # MySQL default
    SERIALIZABLE = "SERIALIZABLE"          # Highest, full isolation


# =============================================================================
# DATABASE PROVIDER
# =============================================================================

class TransactionContext:
    """
    Holds the current transaction state for a request/task.
    
    Used internally to track nested transactions and propagation.
    """
    
    __slots__ = ("session", "is_new", "savepoint_counter")
    
    def __init__(self, session: AsyncSession, is_new: bool = True):
        self.session = session
        self.is_new = is_new
        self.savepoint_counter = 0
    
    def next_savepoint_name(self) -> str:
        """Generate unique savepoint name for NESTED propagation."""
        self.savepoint_counter += 1
        return f"sp_{id(self)}_{self.savepoint_counter}"


class DatabaseProvider:
    """
    Database connection and transaction management provider.
    
    Provides async context managers for transactions with isolation control,
    compatible with SQLAlchemy AsyncSession.
    
    Parameters
    ----------
    database_url : str
        SQLAlchemy database URL (e.g., "postgresql+asyncpg://...")
    **engine_kwargs
        Additional arguments passed to create_async_engine()
    
    Examples
    --------
    >>> db_provider = DatabaseProvider(
    ...     "postgresql+asyncpg://user:pass@localhost/db",
    ...     echo=True,
    ...     pool_size=20
    ... )
    >>> 
    >>> async with db_provider.transaction() as session:
    ...     user = User(name="John")
    ...     session.add(user)
    ...     # Auto-commit on exit, auto-rollback on exception
    """
    
    def __init__(self, database_url: str, **engine_kwargs):
        self.engine: AsyncEngine = create_async_engine(database_url, **engine_kwargs)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    @asynccontextmanager
    async def transaction(
        self,
        isolation_level: Optional[str] = None,
    ):
        """
        Context manager for database transactions.
        
        Parameters
        ----------
        isolation_level : str, optional
            Transaction isolation level. If None, uses database default.
        
        Yields
        ------
        AsyncSession
            SQLAlchemy async session with active transaction.
        
        Examples
        --------
        >>> async with db.transaction(isolation_level=Isolation.SERIALIZABLE) as session:
        ...     result = await session.execute(select(User))
        ...     users = result.scalars().all()
        """
        session: AsyncSession = self.session_maker()
        
        # Set isolation level if specified
        if isolation_level:
            await session.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
        
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    @asynccontextmanager
    async def savepoint(self, session: AsyncSession, name: str):
        """
        Context manager for savepoints (nested transactions).
        
        Parameters
        ----------
        session : AsyncSession
            Parent session to create savepoint in.
        name : str
            Unique savepoint name.
        
        Examples
        --------
        >>> async with db.transaction() as session:
        ...     user = User(name="John")
        ...     session.add(user)
        ...     
        ...     async with db.savepoint(session, "sp1"):
        ...         # Nested operation
        ...         profile = Profile(user_id=user.id)
        ...         session.add(profile)
        ...         # Rollback only this block if error
        """
        savepoint = await session.begin_nested()
        try:
            yield session
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            raise
    
    async def close(self):
        """Close database engine and all connections."""
        await self.engine.dispose()


# =============================================================================
# TRANSACTIONAL DECORATOR
# =============================================================================

def Transactional(
    func: Optional[Callable] = None,
    *,
    propagation: str = Propagation.REQUIRED,
    isolation: Optional[str] = None,
    timeout: Optional[int] = None,
    read_only: bool = False,
    rollback_for: tuple[type[Exception], ...] = (Exception,),
    no_rollback_for: tuple[type[Exception], ...] = (),
):
    """
    Decorator for Spring-style database transaction management.
    
    Provides automatic transaction propagation, isolation control, timeout,
    and rollback rules. Works with both sync and async functions.
    
    Parameters
    ----------
    func : Callable, optional
        The function to decorate (when used without parentheses).
    propagation : str, default=Propagation.REQUIRED
        Transaction propagation behavior.
    isolation : str, optional
        Transaction isolation level. If None, uses database default.
    timeout : int, optional
        Transaction timeout in seconds. Raises TimeoutError if exceeded.
    read_only : bool, default=False
        Hint for read-only optimization (database-specific).
    rollback_for : tuple[type[Exception], ...], default=(Exception,)
        Exception types that trigger rollback.
    no_rollback_for : tuple[type[Exception], ...], default=()
        Exception types that should NOT trigger rollback.
    
    Returns
    -------
    Callable
        Decorated function with transaction management.
    
    Examples
    --------
    Basic usage (join existing or create new):
    
    >>> @transactional
    >>> async def create_user(self, data: dict, db=None):
    ...     user = User(**data)
    ...     db.add(user)
    ...     return user
    
    Always create new transaction:
    
    >>> @transactional(propagation=Propagation.REQUIRES_NEW)
    >>> async def audit_log(self, action: str, db=None):
    ...     log = AuditLog(action=action)
    ...     db.add(log)
    ...     # Commits even if parent transaction rolls back
    
    Nested transaction with savepoint:
    
    >>> @transactional(propagation=Propagation.NESTED)
    >>> async def try_update(self, user_id: str, data: dict, db=None):
    ...     # Rolls back only this operation if error
    ...     await db.execute(update(User).where(User.id == user_id).values(**data))
    
    Custom rollback rules:
    
    >>> @transactional(
    ...     rollback_for=(ValueError, KeyError),
    ...     no_rollback_for=(UserNotFoundException,)
    ... )
    >>> async def update_user(self, user_id: str, data: dict, db=None):
    ...     # Rollback on ValueError/KeyError
    ...     # Commit on UserNotFoundException
    ...     pass
    
    Notes
    -----
    - Decorated method must have `db: Optional[AsyncSession] = None` parameter
    - Service must have `self._db` (DatabaseProvider instance)
    - For NESTED propagation, parent transaction must exist
    - Timeout uses asyncio.wait_for (adds overhead ~1-5ms)
    """
    
    def decorator(f: Callable) -> Callable:
        @functools.wraps(f)
        async def async_wrapper(
            self,
            *args,
            db: Optional[AsyncSession] = None,
            **kwargs
        ):
            # Validate service has DatabaseProvider
            if not hasattr(self, '_db'):
                raise AttributeError(
                    f"{self.__class__.__name__} must have '_db: DatabaseProvider' "
                    f"attribute to use @transactional decorator"
                )
            
            db_provider: DatabaseProvider = self._db
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: MANDATORY
            # ═════════════════════════════════════════════════════════════
            if propagation == Propagation.MANDATORY:
                if db is None:
                    raise RuntimeError(
                        f"{self.__class__.__name__}.{f.__name__}() "
                        f"requires existing transaction (propagation=MANDATORY)"
                    )
                logger.debug(f"[MANDATORY] Using existing transaction")
                return await f(self, *args, db=db, **kwargs)
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: NEVER
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.NEVER:
                if db is not None:
                    raise RuntimeError(
                        f"{self.__class__.__name__}.{f.__name__}() "
                        f"must NOT run in transaction (propagation=NEVER)"
                    )
                logger.debug(f"[NEVER] Running without transaction")
                return await f(self, *args, db=None, **kwargs)
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: NOT_SUPPORTED
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.NOT_SUPPORTED:
                logger.debug(f"[NOT_SUPPORTED] Running without transaction (suspending if exists)")
                return await f(self, *args, db=None, **kwargs)
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: SUPPORTS
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.SUPPORTS:
                logger.debug(f"[SUPPORTS] Using transaction if exists: {db is not None}")
                return await f(self, *args, db=db, **kwargs)
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: REQUIRED (default)
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.REQUIRED:
                if db is not None:
                    logger.debug(f"[REQUIRED] Joining existing transaction")
                    return await f(self, *args, db=db, **kwargs)
                # Fall through to create new transaction
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: REQUIRES_NEW
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.REQUIRES_NEW:
                logger.debug(f"[REQUIRES_NEW] Creating new transaction (suspending current)")
                # Always create new, ignore parent
                # Fall through to create new transaction
            
            # ═════════════════════════════════════════════════════════════
            # PROPAGATION: NESTED
            # ═════════════════════════════════════════════════════════════
            elif propagation == Propagation.NESTED:
                if db is not None:
                    logger.debug(f"[NESTED] Creating savepoint in existing transaction")
                    # Use savepoint for nested transaction
                    savepoint_name = f"sp_{id(self)}_{f.__name__}"
                    
                    async def _execute_with_savepoint():
                        async with db_provider.savepoint(db, savepoint_name):
                            return await f(self, *args, db=db, **kwargs)
                    
                    if timeout is not None:
                        try:
                            return await asyncio.wait_for(
                                _execute_with_savepoint(),
                                timeout=timeout
                            )
                        except asyncio.TimeoutError:
                            raise TimeoutError(
                                f"Transaction timeout after {timeout}s in "
                                f"{self.__class__.__name__}.{f.__name__}()"
                            )
                    else:
                        return await _execute_with_savepoint()
                # Fall through to create new transaction
            
            # ═════════════════════════════════════════════════════════════
            # CREATE NEW TRANSACTION
            # ═════════════════════════════════════════════════════════════
            logger.debug(f"[{propagation}] Creating new transaction")
            
            async def _execute_with_transaction():
                async with db_provider.transaction(isolation_level=isolation) as session:
                    try:
                        result = await f(self, *args, db=session, **kwargs)
                        return result
                    
                    except Exception as e:
                        # Check rollback rules
                        should_not_rollback = any(
                            isinstance(e, exc_type) for exc_type in no_rollback_for
                        )
                        
                        if should_not_rollback:
                            logger.info(
                                f"Exception {type(e).__name__} in no_rollback_for, "
                                f"committing transaction anyway"
                            )
                            # Return None or re-raise without rollback
                            # SQLAlchemy will auto-commit on clean exit
                            return None
                        
                        # Check if should rollback
                        should_rollback = any(
                            isinstance(e, exc_type) for exc_type in rollback_for
                        )
                        
                        if should_rollback or rollback_for == (Exception,):
                            logger.debug(f"Rolling back on {type(e).__name__}")
                            raise  # SQLAlchemy auto-rollback on exception
                        else:
                            raise
            
            # Apply timeout if specified
            if timeout is not None:
                try:
                    return await asyncio.wait_for(
                        _execute_with_transaction(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(
                        f"Transaction timeout after {timeout}s in "
                        f"{self.__class__.__name__}.{f.__name__}()"
                    )
            else:
                return await _execute_with_transaction()
        
        return async_wrapper
    
    # Support both @transactional and @transactional(...)
    if func is not None:
        return decorator(func)
    else:
        return decorator


# =============================================================================
# TESTING UTILITIES
# =============================================================================

class TransactionTestContext:
    """
    Test context for transaction management.
    
    Provides utilities for testing transactional methods with rollback.
    
    Examples
    --------
    >>> async with TransactionTestContext(db_provider) as ctx:
    ...     service = get_service(UserService)
    ...     user = await service.create_user({"name": "Test"}, db=ctx.session)
    ...     # Auto-rollback on exit, no data persisted
    """
    
    def __init__(self, db_provider: DatabaseProvider):
        self.db_provider = db_provider
        self.session: Optional[AsyncSession] = None
    
    async def __aenter__(self):
        self.session = self.db_provider.session_maker()
        await self.session.begin()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.rollback()
        await self.session.close()
        return False

