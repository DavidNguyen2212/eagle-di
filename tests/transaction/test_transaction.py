"""
Unit Tests for Spring-Style Transactional Decorator
====================================================

Tests all 7 propagation behaviors, isolation levels, timeout,
and rollback rules inspired by Spring's @Transactional.

Run with: pytest tests/test_transaction.py -v
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

from app.core.transaction import (
    Transactional,
    Propagation,
    Isolation,
    TransactionContext,
    TransactionTestContext,
)


# =============================================================================
# Mock Fixtures
# =============================================================================


class MockAsyncSession:
    """Mock SQLAlchemy AsyncSession for testing."""
    
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.items_added = []
        self._savepoints = []
    
    async def commit(self):
        self.committed = True
    
    async def rollback(self):
        self.rolled_back = True
    
    async def close(self):
        self.closed = True
    
    async def begin(self):
        pass
    
    def add(self, item):
        self.items_added.append(item)
    
    async def execute(self, query):
        pass
    
    async def flush(self):
        pass
    
    async def refresh(self, obj):
        pass
    
    async def begin_nested(self):
        """Mock savepoint creation."""
        savepoint = MockSavepoint()
        self._savepoints.append(savepoint)
        return savepoint


class MockSavepoint:
    """Mock savepoint for NESTED propagation testing."""
    
    def __init__(self):
        self.committed = False
        self.rolled_back = False
    
    async def commit(self):
        self.committed = True
    
    async def rollback(self):
        self.rolled_back = True


class MockDatabaseProvider:
    """Mock DatabaseProvider for testing without real database."""
    
    def __init__(self):
        self.sessions = []
        self._current_session = None
        self._isolation_levels = []
    
    def session_maker(self):
        session = MockAsyncSession()
        self.sessions.append(session)
        self._current_session = session
        return session
    
    @asynccontextmanager
    async def transaction(self, isolation_level=None):
        """Async context manager for transaction."""
        self._isolation_levels.append(isolation_level)
        session = self.session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    @asynccontextmanager
    async def savepoint(self, session, name):
        """Async context manager for savepoint."""
        savepoint = await session.begin_nested()
        try:
            yield session
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            raise


@pytest.fixture
def mock_db_provider():
    """Fixture providing a mock DatabaseProvider."""
    return MockDatabaseProvider()


# =============================================================================
# Test: TransactionContext
# =============================================================================


class TestTransactionContext:
    """Tests for TransactionContext helper class."""
    
    def test_init_with_session(self):
        """TransactionContext stores session and is_new flag."""
        session = MockAsyncSession()
        ctx = TransactionContext(session, is_new=True)
        
        assert ctx.session is session
        assert ctx.is_new is True
        assert ctx.savepoint_counter == 0
    
    def test_next_savepoint_name_increments(self):
        """Savepoint names are unique and incrementing."""
        session = MockAsyncSession()
        ctx = TransactionContext(session)
        
        name1 = ctx.next_savepoint_name()
        name2 = ctx.next_savepoint_name()
        name3 = ctx.next_savepoint_name()
        
        assert name1 != name2 != name3
        assert "_1" in name1
        assert "_2" in name2
        assert "_3" in name3


# =============================================================================
# Test: Propagation.REQUIRED (Default)
# =============================================================================


class TestPropagationRequired:
    """Tests for REQUIRED propagation (join existing or create new)."""
    
    @pytest.mark.asyncio
    async def test_creates_new_transaction_when_none_exists(self, mock_db_provider):
        """REQUIRED creates new transaction if no current transaction."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def do_work(self, db=None):
                db.add({"name": "test"})
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"
        assert len(mock_db_provider.sessions) == 1
        session = mock_db_provider.sessions[0]
        assert session.committed is True
        assert session.closed is True
    
    @pytest.mark.asyncio
    async def test_joins_existing_transaction(self, mock_db_provider):
        """REQUIRED joins existing transaction if one is passed."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def do_work(self, db=None):
                db.add({"name": "test"})
                return "done"
        
        service = MyService()
        result = await service.do_work(db=existing_session)
        
        assert result == "done"
        # Should use existing session, not create new
        assert len(mock_db_provider.sessions) == 0
        assert {"name": "test"} in existing_session.items_added
    
    @pytest.mark.asyncio
    async def test_nested_calls_share_transaction(self, mock_db_provider):
        """Nested REQUIRED calls share the same transaction."""
        
        class OuterService:
            def __init__(self, inner):
                self._db = mock_db_provider
                self.inner = inner
            
            @Transactional
            async def outer_method(self, db=None):
                db.add({"outer": True})
                await self.inner.inner_method(db=db)
                return "outer done"
        
        class InnerService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def inner_method(self, db=None):
                db.add({"inner": True})
                return "inner done"
        
        inner = InnerService()
        outer = OuterService(inner)
        
        result = await outer.outer_method()
        
        assert result == "outer done"
        # Only one transaction created
        assert len(mock_db_provider.sessions) == 1
        session = mock_db_provider.sessions[0]
        assert {"outer": True} in session.items_added
        assert {"inner": True} in session.items_added


# =============================================================================
# Test: Propagation.REQUIRES_NEW
# =============================================================================


class TestPropagationRequiresNew:
    """Tests for REQUIRES_NEW propagation (always create new)."""
    
    @pytest.mark.asyncio
    async def test_creates_new_even_with_existing(self, mock_db_provider):
        """REQUIRES_NEW always creates new transaction, suspending current."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def do_work(self, db=None):
                db.add({"name": "new_tx"})
                return "done"
        
        service = MyService()
        result = await service.do_work(db=existing_session)
        
        assert result == "done"
        # Creates new session, ignores existing
        assert len(mock_db_provider.sessions) == 1
        new_session = mock_db_provider.sessions[0]
        assert {"name": "new_tx"} in new_session.items_added
        # Existing session untouched
        assert len(existing_session.items_added) == 0
    
    @pytest.mark.asyncio
    async def test_commits_independently(self, mock_db_provider):
        """REQUIRES_NEW transaction commits even if parent fails."""
        
        class AuditService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def log_action(self, action: str, db=None):
                db.add({"action": action})
                return True
        
        class MainService:
            def __init__(self, audit):
                self._db = mock_db_provider
                self.audit = audit
            
            @Transactional
            async def do_work(self, should_fail: bool, db=None):
                db.add({"main": True})
                await self.audit.log_action("started", db=db)
                if should_fail:
                    raise ValueError("Main operation failed")
                return "success"
        
        audit = AuditService()
        main = MainService(audit)
        
        with pytest.raises(ValueError):
            await main.do_work(should_fail=True)
        
        # Main transaction rolled back
        main_session = mock_db_provider.sessions[0]
        assert main_session.rolled_back is True
        
        # Audit transaction committed independently
        audit_session = mock_db_provider.sessions[1]
        assert audit_session.committed is True


# =============================================================================
# Test: Propagation.MANDATORY
# =============================================================================


class TestPropagationMandatory:
    """Tests for MANDATORY propagation (must have existing transaction)."""
    
    @pytest.mark.asyncio
    async def test_raises_when_no_transaction(self, mock_db_provider):
        """MANDATORY raises error if no current transaction."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def do_work(self, db=None):
                return "done"
        
        service = MyService()
        
        with pytest.raises(RuntimeError, match="requires existing transaction"):
            await service.do_work()
    
    @pytest.mark.asyncio
    async def test_works_with_existing_transaction(self, mock_db_provider):
        """MANDATORY works fine with existing transaction."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def do_work(self, db=None):
                db.add({"mandatory": True})
                return "done"
        
        service = MyService()
        result = await service.do_work(db=existing_session)
        
        assert result == "done"
        assert {"mandatory": True} in existing_session.items_added


# =============================================================================
# Test: Propagation.SUPPORTS
# =============================================================================


class TestPropagationSupports:
    """Tests for SUPPORTS propagation (join if exists, otherwise non-tx)."""
    
    @pytest.mark.asyncio
    async def test_uses_transaction_if_exists(self, mock_db_provider):
        """SUPPORTS uses existing transaction if available."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.SUPPORTS)
            async def do_work(self, db=None):
                if db:
                    db.add({"supports": True})
                return "done"
        
        service = MyService()
        result = await service.do_work(db=existing_session)
        
        assert result == "done"
        assert {"supports": True} in existing_session.items_added
    
    @pytest.mark.asyncio
    async def test_runs_without_transaction_if_none(self, mock_db_provider):
        """SUPPORTS runs without transaction if none exists."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.SUPPORTS)
            async def do_work(self, db=None):
                return f"db_is_none={db is None}"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "db_is_none=True"
        assert len(mock_db_provider.sessions) == 0


# =============================================================================
# Test: Propagation.NOT_SUPPORTED
# =============================================================================


class TestPropagationNotSupported:
    """Tests for NOT_SUPPORTED propagation (always non-transactional)."""
    
    @pytest.mark.asyncio
    async def test_suspends_existing_transaction(self, mock_db_provider):
        """NOT_SUPPORTED suspends any existing transaction."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NOT_SUPPORTED)
            async def do_work(self, db=None):
                return f"db_is_none={db is None}"
        
        service = MyService()
        result = await service.do_work(db=existing_session)
        
        # Existing session is ignored
        assert result == "db_is_none=True"
    
    @pytest.mark.asyncio
    async def test_runs_non_transactional(self, mock_db_provider):
        """NOT_SUPPORTED always runs without transaction."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NOT_SUPPORTED)
            async def do_work(self, db=None):
                assert db is None
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"


# =============================================================================
# Test: Propagation.NEVER
# =============================================================================


class TestPropagationNever:
    """Tests for NEVER propagation (must NOT have transaction)."""
    
    @pytest.mark.asyncio
    async def test_raises_when_transaction_exists(self, mock_db_provider):
        """NEVER raises error if transaction exists."""
        
        existing_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NEVER)
            async def do_work(self, db=None):
                return "done"
        
        service = MyService()
        
        with pytest.raises(RuntimeError, match="must NOT run in transaction"):
            await service.do_work(db=existing_session)
    
    @pytest.mark.asyncio
    async def test_works_without_transaction(self, mock_db_provider):
        """NEVER works fine without transaction."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NEVER)
            async def do_work(self, db=None):
                assert db is None
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"


# =============================================================================
# Test: Propagation.NESTED
# =============================================================================


class TestPropagationNested:
    """Tests for NESTED propagation (savepoint if parent exists)."""
    
    @pytest.mark.asyncio
    async def test_creates_savepoint_with_parent(self, mock_db_provider):
        """NESTED creates savepoint when parent transaction exists."""
        
        parent_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NESTED)
            async def try_update(self, db=None):
                db.add({"nested": True})
                return "done"
        
        service = MyService()
        result = await service.try_update(db=parent_session)
        
        assert result == "done"
        assert {"nested": True} in parent_session.items_added
        # Savepoint was created
        assert len(parent_session._savepoints) == 1
        assert parent_session._savepoints[0].committed is True
    
    @pytest.mark.asyncio
    async def test_savepoint_rollback_on_error(self, mock_db_provider):
        """NESTED rolls back only savepoint on error, parent continues."""
        
        parent_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NESTED)
            async def try_update(self, should_fail: bool, db=None):
                db.add({"nested": True})
                if should_fail:
                    raise ValueError("Nested operation failed")
                return "done"
        
        service = MyService()
        
        with pytest.raises(ValueError):
            await service.try_update(should_fail=True, db=parent_session)
        
        # Savepoint rolled back, not the parent
        assert len(parent_session._savepoints) == 1
        assert parent_session._savepoints[0].rolled_back is True
        # Parent session not rolled back directly
        assert parent_session.rolled_back is False
    
    @pytest.mark.asyncio
    async def test_creates_new_transaction_when_no_parent(self, mock_db_provider):
        """NESTED creates new transaction if no parent exists."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NESTED)
            async def do_work(self, db=None):
                db.add({"nested_no_parent": True})
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"
        assert len(mock_db_provider.sessions) == 1


# =============================================================================
# Test: Isolation Levels
# =============================================================================


class TestIsolationLevels:
    """Tests for transaction isolation levels."""
    
    @pytest.mark.asyncio
    async def test_isolation_read_committed(self, mock_db_provider):
        """Isolation level is set when specified."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(isolation=Isolation.READ_COMMITTED)
            async def do_work(self, db=None):
                return "done"
        
        service = MyService()
        await service.do_work()
        
        assert Isolation.READ_COMMITTED in mock_db_provider._isolation_levels
    
    @pytest.mark.asyncio
    async def test_isolation_serializable(self, mock_db_provider):
        """SERIALIZABLE isolation level is passed correctly."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(isolation=Isolation.SERIALIZABLE)
            async def do_work(self, db=None):
                return "done"
        
        service = MyService()
        await service.do_work()
        
        assert Isolation.SERIALIZABLE in mock_db_provider._isolation_levels


# =============================================================================
# Test: Timeout
# =============================================================================


class TestTimeout:
    """Tests for transaction timeout."""
    
    @pytest.mark.asyncio
    async def test_timeout_raises_on_slow_operation(self, mock_db_provider):
        """Timeout raises TimeoutError for slow operations."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(timeout=1)
            async def slow_work(self, db=None):
                await asyncio.sleep(2)
                return "done"
        
        service = MyService()
        
        with pytest.raises(TimeoutError, match="timeout after 1s"):
            await service.slow_work()
    
    @pytest.mark.asyncio
    async def test_timeout_succeeds_for_fast_operation(self, mock_db_provider):
        """Fast operations complete within timeout."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(timeout=5)
            async def fast_work(self, db=None):
                await asyncio.sleep(0.1)
                return "done"
        
        service = MyService()
        result = await service.fast_work()
        
        assert result == "done"
    
    @pytest.mark.asyncio
    async def test_timeout_with_nested_propagation(self, mock_db_provider):
        """Timeout works with NESTED propagation."""
        
        parent_session = MockAsyncSession()
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NESTED, timeout=1)
            async def slow_nested(self, db=None):
                await asyncio.sleep(2)
                return "done"
        
        service = MyService()
        
        with pytest.raises(TimeoutError):
            await service.slow_nested(db=parent_session)


# =============================================================================
# Test: Rollback Rules
# =============================================================================


class TestRollbackRules:
    """Tests for rollback_for and no_rollback_for rules."""
    
    @pytest.mark.asyncio
    async def test_rollback_for_specific_exceptions(self, mock_db_provider):
        """rollback_for only rolls back on specified exceptions."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(rollback_for=(ValueError,))
            async def do_work(self, error_type: str, db=None):
                db.add({"data": True})
                if error_type == "value":
                    raise ValueError("Value error")
                elif error_type == "key":
                    raise KeyError("Key error")
                return "done"
        
        service = MyService()
        
        # ValueError should rollback
        with pytest.raises(ValueError):
            await service.do_work("value")
        
        assert mock_db_provider.sessions[0].rolled_back is True
    
    @pytest.mark.asyncio
    async def test_no_rollback_for_exceptions(self, mock_db_provider):
        """no_rollback_for commits even when exception occurs."""
        
        class UserNotFoundError(Exception):
            pass
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(no_rollback_for=(UserNotFoundError,))
            async def find_user(self, user_id: str, db=None):
                db.add({"searched": user_id})
                if user_id == "not_found":
                    raise UserNotFoundError("User not found")
                return {"id": user_id}
        
        service = MyService()
        
        # UserNotFoundError should NOT cause rollback
        result = await service.find_user("not_found")
        
        # Result is None (as per implementation)
        assert result is None
        # Transaction was NOT rolled back
        session = mock_db_provider.sessions[0]
        assert session.rolled_back is False
    
    @pytest.mark.asyncio
    async def test_default_rollback_on_any_exception(self, mock_db_provider):
        """Default behavior rolls back on any exception."""
        
        class CustomError(Exception):
            pass
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def do_work(self, db=None):
                db.add({"data": True})
                raise CustomError("Something went wrong")
        
        service = MyService()
        
        with pytest.raises(CustomError):
            await service.do_work()
        
        assert mock_db_provider.sessions[0].rolled_back is True


# =============================================================================
# Test: Decorator Validation
# =============================================================================


class TestDecoratorValidation:
    """Tests for decorator validation and error handling."""
    
    @pytest.mark.asyncio
    async def test_raises_without_db_attribute(self, mock_db_provider):
        """Raises AttributeError if service lacks _db attribute."""
        
        class BadService:
            # Missing _db attribute
            
            @Transactional
            async def do_work(self, db=None):
                return "done"
        
        service = BadService()
        
        with pytest.raises(AttributeError, match="must have '_db: DatabaseProvider'"):
            await service.do_work()
    
    @pytest.mark.asyncio
    async def test_decorator_without_parentheses(self, mock_db_provider):
        """Decorator works without parentheses (@Transactional)."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def do_work(self, db=None):
                db.add({"no_parens": True})
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"
    
    @pytest.mark.asyncio
    async def test_decorator_with_parentheses(self, mock_db_provider):
        """Decorator works with empty parentheses (@Transactional())."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional()
            async def do_work(self, db=None):
                db.add({"with_parens": True})
                return "done"
        
        service = MyService()
        result = await service.do_work()
        
        assert result == "done"
    
    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self, mock_db_provider):
        """Decorator preserves function name and docstring."""
        
        class MyService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional
            async def create_user(self, name: str, db=None):
                """Create a new user with given name."""
                return {"name": name}
        
        service = MyService()
        
        assert service.create_user.__name__ == "create_user"
        assert "Create a new user" in service.create_user.__doc__


# =============================================================================
# Test: TransactionTestContext
# =============================================================================


class TestTransactionTestContext:
    """Tests for TransactionTestContext testing utility."""
    
    @pytest.mark.asyncio
    async def test_provides_session(self):
        """TransactionTestContext provides a usable session."""
        
        mock_provider = MockDatabaseProvider()
        
        async with TransactionTestContext(mock_provider) as ctx:
            assert ctx.session is not None
    
    @pytest.mark.asyncio
    async def test_auto_rollback_on_exit(self):
        """TransactionTestContext auto-rolls back on exit."""
        
        mock_provider = MockDatabaseProvider()
        
        async with TransactionTestContext(mock_provider) as ctx:
            ctx.session.add({"test": True})
        
        # Session should be rolled back and closed
        session = mock_provider.sessions[0]
        assert session.rolled_back is True
        assert session.closed is True


# =============================================================================
# Test: Complex Scenarios
# =============================================================================


class TestComplexScenarios:
    """Tests for complex real-world scenarios."""
    
    @pytest.mark.asyncio
    async def test_repository_service_pattern(self, mock_db_provider):
        """Test typical repository-service pattern with transactions."""
        
        class UserRepository:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def create(self, data: dict, db=None):
                db.add(data)
                return data
        
        class UserService:
            def __init__(self, repo):
                self._db = mock_db_provider
                self.repo = repo
            
            @Transactional
            async def create_user(self, name: str, db=None):
                user = await self.repo.create({"name": name}, db=db)
                return user
        
        repo = UserRepository()
        service = UserService(repo)
        
        user = await service.create_user("John")
        
        assert user == {"name": "John"}
        assert len(mock_db_provider.sessions) == 1
    
    @pytest.mark.asyncio
    async def test_audit_log_pattern(self, mock_db_provider):
        """Test audit logging that persists even on failure."""
        
        audit_logs = []
        
        class AuditService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def log(self, message: str, db=None):
                audit_logs.append(message)
                db.add({"audit": message})
                return True
        
        class OrderService:
            def __init__(self, audit):
                self._db = mock_db_provider
                self.audit = audit
            
            @Transactional
            async def create_order(self, data: dict, should_fail: bool, db=None):
                await self.audit.log("Order started")
                db.add({"order": data})
                if should_fail:
                    raise ValueError("Order failed")
                await self.audit.log("Order completed")
                return data
        
        audit = AuditService()
        orders = OrderService(audit)
        
        with pytest.raises(ValueError):
            await orders.create_order({"item": "phone"}, should_fail=True)
        
        # Audit log persisted despite order failure
        assert "Order started" in audit_logs
        # Order transaction rolled back
        assert mock_db_provider.sessions[0].rolled_back is True
        # Audit transaction committed
        assert mock_db_provider.sessions[1].committed is True
    
    @pytest.mark.asyncio
    async def test_partial_rollback_with_nested(self, mock_db_provider):
        """Test partial rollback using NESTED propagation."""
        
        class InventoryService:
            def __init__(self):
                self._db = mock_db_provider
            
            @Transactional(propagation=Propagation.NESTED)
            async def reserve_item(self, item_id: str, should_fail: bool, db=None):
                db.add({"reserve": item_id})
                if should_fail:
                    raise ValueError(f"Cannot reserve {item_id}")
                return True
        
        class OrderService:
            def __init__(self, inventory):
                self._db = mock_db_provider
                self.inventory = inventory
            
            @Transactional
            async def create_order(self, items: list, db=None):
                results = []
                for item in items:
                    try:
                        await self.inventory.reserve_item(
                            item["id"], 
                            item.get("should_fail", False),
                            db=db
                        )
                        results.append({"item": item["id"], "reserved": True})
                    except ValueError:
                        results.append({"item": item["id"], "reserved": False})
                
                db.add({"order": results})
                return results
        
        inventory = InventoryService()
        orders = OrderService(inventory)
        
        items = [
            {"id": "item1"},
            {"id": "item2", "should_fail": True},  # This will fail
            {"id": "item3"},
        ]
        
        result = await orders.create_order(items)
        
        # Item2 failed but order still completed
        assert result[0] == {"item": "item1", "reserved": True}
        assert result[1] == {"item": "item2", "reserved": False}
        assert result[2] == {"item": "item3", "reserved": True}
        
        # Main transaction committed
        session = mock_db_provider.sessions[0]
        assert session.committed is True


# =============================================================================
# Test: Isolation Level & Propagation Constants
# =============================================================================


class TestIsolationConstants:
    """Tests to verify isolation level constant values."""
    
    def test_isolation_values(self):
        """Isolation levels have correct SQL values."""
        assert Isolation.READ_UNCOMMITTED == "READ UNCOMMITTED"
        assert Isolation.READ_COMMITTED == "READ COMMITTED"
        assert Isolation.REPEATABLE_READ == "REPEATABLE READ"
        assert Isolation.SERIALIZABLE == "SERIALIZABLE"


class TestPropagationConstants:
    """Tests to verify propagation constant values."""
    
    def test_propagation_values(self):
        """Propagation behaviors have correct values."""
        assert Propagation.REQUIRED == "REQUIRED"
        assert Propagation.REQUIRES_NEW == "REQUIRES_NEW"
        assert Propagation.MANDATORY == "MANDATORY"
        assert Propagation.SUPPORTS == "SUPPORTS"
        assert Propagation.NOT_SUPPORTED == "NOT_SUPPORTED"
        assert Propagation.NEVER == "NEVER"
        assert Propagation.NESTED == "NESTED"
