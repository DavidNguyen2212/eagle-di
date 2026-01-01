"""
FastAPI Dependency Injection Utility
======================================

A lightweight, type-hint based dependency injection system for FastAPI,
inspired by NestJS and Spring Boot patterns. Zero dependencies, copy-paste ready.

Features:
    - Automatic injection via type hints
    - Singleton scope by default
    - Circular dependency resolution (use as last resort - prefer refactoring)
    - Lifecycle hooks (on_init, on_destroy)
    - Testing utilities (override, test_container)

Quick Start:
    >>> from app.core.eagle_di import Injectable, AutoInject
    >>>
    >>> @Injectable
    >>> class UserService:
    >>>     def get_user(self, id: str) -> dict:
    >>>         return {"id": id}
    >>>
    >>> @router.get("/users/{id}")
    >>> @AutoInject
    >>> async def get_user(id: str, service: UserService):
    >>>     return service.get_user(id)

Author: David Nguyen (Nguyen Duc An)
"""

from __future__ import annotations

import inspect
import logging
import os
from functools import lru_cache
from threading import Lock
from typing import (
    Annotated,
    Any,
    Callable,
    Dict,
    Type,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from fastapi import Depends
from fastapi.params import Depends as DependsType

__all__ = [
    # Core decorators
    "Injectable",
    "AutoInject",
    "Controller",
    # Dependency providers
    "Provide",
    "get_service",
    # Circular dependency support
    "ForwardRef",
    "forwardRef",
    "Inject",
    # Testing utilities
    "override",
    "test_container",
    "clear_registry",
    # Lifecycle
    "shutdown_all",
    "async_shutdown_all",
]

logger = logging.getLogger(__name__)
T = TypeVar("T")

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

_registry: Dict[Type, Callable] = {}
_instances: Dict[Type, Any] = {}
_lock = Lock()
_VERBOSE = os.environ.get("DI_VERBOSE", "0") == "1"


def _log(msg: str) -> None:
    """Log message if DI_VERBOSE=1 is set."""
    if _VERBOSE:
        try:
            print(msg)
        except UnicodeEncodeError:
            # Fallback for Windows console that can't handle emoji
            print(msg.encode('ascii', 'replace').decode('ascii'))


# -----------------------------------------------------------------------------
# Forward Reference Support
# -----------------------------------------------------------------------------


class ForwardRef:
    """
    Lazy type reference for handling circular dependencies.
    
    Use `forwardRef()` function instead of instantiating directly.
    """
    
    __slots__ = ("_type_getter", "_resolved_type")

    def __init__(self, type_getter: Callable[[], Type]) -> None:
        self._type_getter = type_getter
        self._resolved_type: Type | None = None

    def resolve(self) -> Type:
        """Resolve and cache the forward reference."""
        if self._resolved_type is None:
            self._resolved_type = self._type_getter()
        return self._resolved_type

    def __repr__(self) -> str:
        if self._resolved_type:
            return f"ForwardRef({self._resolved_type.__name__})"
        return "ForwardRef(<unresolved>)"


def forwardRef(type_getter: Callable[[], Type[T]]) -> Type[T]:
    """
    Create a lazy type reference for circular dependency resolution.
    
    Args:
        type_getter: Lambda that returns the target type.
    
    Returns:
        ForwardRef wrapper resolved at injection time.
    
    Example:
        >>> @Injectable
        >>> class ServiceA:
        >>>     def __init__(self, b: forwardRef(lambda: ServiceB)):
        >>>         self.b = b
    """
    return ForwardRef(type_getter)  # type: ignore


# -----------------------------------------------------------------------------
# Lazy Injection (for TRUE circular dependencies)
# -----------------------------------------------------------------------------


class LazyInject:
    """
    Marker for lazy injection that returns a getter function.
    
    Use `Inject()` function instead of instantiating directly.
    """
    
    __slots__ = ("_forward_ref",)

    def __init__(self, forward_ref: ForwardRef) -> None:
        self._forward_ref = forward_ref

    @property
    def forward_ref(self) -> ForwardRef:
        return self._forward_ref

    def __repr__(self) -> str:
        return f"LazyInject({self._forward_ref})"


def Inject(forward_ref: ForwardRef) -> LazyInject:
    """
    Create a lazy injection that returns a getter function instead of instance.
    
    Use for TRUE circular dependencies (A ↔ B) where both sides need each other.
    
    Args:
        forward_ref: A ForwardRef created by forwardRef().
    
    Returns:
        LazyInject marker that injects Callable[[], Type].
    
    Example:
        >>> @Injectable
        >>> class ServiceA:
        >>>     def __init__(self, get_b: Inject(forwardRef(lambda: ServiceB))):
        >>>         self._get_b = get_b  # Callable[[], ServiceB]
        >>>     
        >>>     def use_b(self):
        >>>         return self._get_b().some_method()
    """
    if not isinstance(forward_ref, ForwardRef):
        raise TypeError(f"Inject() requires forwardRef(), got {type(forward_ref)}")
    return LazyInject(forward_ref)


# -----------------------------------------------------------------------------
# Internal Resolution Functions
# -----------------------------------------------------------------------------


def _resolve_service_recursive(cls: Type, depth: int = 0) -> Any:
    """Recursively resolve a service and all its @Injectable dependencies."""
    if depth > 30:
        raise RecursionError(f"Circular dependency too deep: {cls.__name__}")

    if cls not in _registry:
        raise ValueError(f"{cls.__name__} is not @Injectable")

    init = cls.__init__
    try:
        hints = get_type_hints(init, include_extras=True)
    except Exception:
        hints = getattr(init, "__annotations__", {})

    sig = inspect.signature(init)
    kwargs = {}

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        ann = hints.get(name, param.annotation)

        if get_origin(ann) is Annotated:
            ann, *_ = get_args(ann)

        if isinstance(ann, LazyInject):
            fwd = ann.forward_ref
            kwargs[name] = lambda f=fwd: _resolve_service_recursive(f.resolve(), depth + 1)
        elif isinstance(ann, ForwardRef):
            # Resolve ForwardRef and recursively resolve the target
            resolved = ann.resolve()
            kwargs[name] = _resolve_service_recursive(resolved, depth + 1)
        elif ann in _registry:
            kwargs[name] = _resolve_service_recursive(ann, depth + 1)
        elif param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default

    return cls(**kwargs)


def _create_lazy_getter(forward_ref: ForwardRef) -> DependsType:
    """Create a Depends() that returns a getter function."""
    def getter_provider() -> Callable:
        def get_instance():
            resolved_type = forward_ref.resolve()
            if resolved_type not in _registry:
                raise ValueError(f"{resolved_type.__name__} is not @Injectable")
            return _resolve_service_recursive(resolved_type)
        return get_instance

    getter_provider.__signature__ = inspect.Signature(return_annotation=Callable)
    getter_provider.__name__ = f"lazy_getter_{id(forward_ref)}"
    return Depends(getter_provider)


def _create_lazy_depends(forward_ref: ForwardRef) -> DependsType:
    """Create a lazy Depends() that resolves ForwardRef at runtime."""
    resolved_type = None
    resolved_provider = None

    try:
        resolved_type = forward_ref.resolve()
        if resolved_type in _registry:
            resolved_provider = _registry[resolved_type]
    except Exception:
        pass

    def lazy_provider(**kwargs):
        nonlocal resolved_type
        if resolved_type is None:
            resolved_type = forward_ref.resolve()
        if resolved_type not in _registry:
            raise ValueError(f"{resolved_type.__name__} is not @Injectable")
        return _registry[resolved_type](**kwargs)

    if resolved_provider is not None:
        lazy_provider.__signature__ = inspect.signature(resolved_provider)
    else:
        lazy_provider.__signature__ = inspect.Signature(return_annotation=object)

    lazy_provider.__name__ = f"lazy_{id(forward_ref)}"
    return Depends(lazy_provider)


@lru_cache(maxsize=256)
def _get_cached_type_hints(func) -> Dict[str, Type]:
    """Cache type hints to avoid repeated introspection."""
    try:
        return get_type_hints(func, include_extras=True)
    except Exception:
        return getattr(func, "__annotations__", {})


def _call_on_init(instance: Any) -> None:
    """Call on_init() lifecycle hook if defined."""
    if hasattr(instance, "on_init") and callable(instance.on_init):
        result = instance.on_init()
        if inspect.iscoroutine(result):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)
            except RuntimeError:
                asyncio.run(result)


def _build_provider(cls: Type, params: list[inspect.Parameter]) -> Callable:
    """Build a singleton provider function for the given class."""
    valid_params = [
        p for p in params
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    param_names = tuple(p.name for p in valid_params)

    if not param_names:
        def provider():
            if cls in _instances:
                return _instances[cls]
            instance = cls()
            _instances[cls] = instance
            _call_on_init(instance)
            return instance

        provider.__signature__ = inspect.Signature(return_annotation=cls)
    else:
        def provider(**kwargs):
            if cls in _instances:
                return _instances[cls]
            instance = cls(**{k: kwargs[k] for k in param_names})
            _instances[cls] = instance
            _call_on_init(instance)
            return instance

        provider.__signature__ = inspect.Signature(
            parameters=valid_params,
            return_annotation=cls,
        )

    provider.__name__ = f"get_{cls.__name__}"
    return provider


# -----------------------------------------------------------------------------
# Core Decorators
# -----------------------------------------------------------------------------


def Injectable(cls: Type[T]) -> Type[T]:
    """
    Mark a class as injectable with singleton scope.
    
    Dependencies are automatically resolved from type hints.
    
    Args:
        cls: The class to register.
    
    Returns:
        The same class with injection metadata.
    
    Example:
        >>> @Injectable
        >>> class UserService:
        >>>     def __init__(self, repo: UserRepository):
        >>>         self.repo = repo
    """
    _log(f"\n{'='*60}")
    _log(f"🔧 Registering Injectable: {cls.__name__}")
    _log(f"   Module: {cls.__module__}")

    init = cls.__init__
    if inspect.iscoroutinefunction(init):
        raise TypeError(f"{cls.__name__}.__init__ cannot be async")

    sig = inspect.signature(init)
    type_hints = _get_cached_type_hints(init)
    params: list[inspect.Parameter] = []
    dep_count = 0

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = type_hints.get(name, param.annotation)
        default = inspect.Parameter.empty
        dep_type = "❌ no injection"

        if get_origin(annotation) is Annotated:
            actual_type, *meta = get_args(annotation)
            depends = next((m for m in meta if isinstance(m, DependsType)), None)

            if depends:
                default, annotation, dep_type = depends, actual_type, "🔗 explicit Depends()"
                dep_count += 1
            elif isinstance(actual_type, ForwardRef):
                default, annotation, dep_type = _create_lazy_depends(actual_type), object, "🔄 forwardRef"
                dep_count += 1
            elif actual_type in _registry:
                default, annotation, dep_type = Depends(_registry[actual_type]), actual_type, "✨ auto-inject"
                dep_count += 1

        elif isinstance(annotation, ForwardRef):
            default, annotation, dep_type = _create_lazy_depends(annotation), object, "🔄 forwardRef"
            dep_count += 1

        elif isinstance(annotation, LazyInject):
            default, annotation, dep_type = _create_lazy_getter(annotation.forward_ref), Callable, "🔁 Inject(forwardRef)"
            dep_count += 1

        elif annotation in _registry:
            default, dep_type = Depends(_registry[annotation]), "✨ auto-inject"
            dep_count += 1

        elif param.default is not inspect.Parameter.empty:
            default, dep_type = param.default, f"📌 default"

        type_name = getattr(annotation, "__name__", str(annotation))
        _log(f"   ├─ {name}: {type_name} {dep_type}")

        params.append(inspect.Parameter(
            name=name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=default,
            annotation=annotation,
        ))

    provider = _build_provider(cls, params)

    with _lock:
        _registry[cls] = provider

    cls.__injectable__ = True
    cls.__provider__ = provider

    _log(f"   ✅ Total dependencies: {dep_count}")
    _log(f"{'='*60}\n")

    return cls


def AutoInject(func: Callable) -> Callable:
    """
    Automatically inject dependencies into a FastAPI endpoint.
    
    Args:
        func: The endpoint function to process.
    
    Returns:
        The function with updated signature for FastAPI.
    
    Warning:
        Place injectable services AFTER required path/query params.
        Python doesn't allow non-default args after default args.
        
        # ❌ Wrong - will raise syntax error
        def get_user(service: UserService, id: int): ...
        
        # ✅ Correct - service after required params
        def get_user(id: int, service: UserService): ...
    
    Example:
        >>> @router.get("/users/{id}")
        >>> @AutoInject
        >>> async def get_user(id: str, service: UserService):
        >>>     return service.get_user(id)
    """
    _log(f"\n{'─'*60}")
    _log(f"🎯 Auto-injecting endpoint: {func.__name__}")

    sig = inspect.signature(func)
    type_hints = _get_cached_type_hints(func)
    new_params = []
    injected = 0

    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        annotation = type_hints.get(name, param.annotation)
        default = param.default
        status = "➖ no inject"

        if get_origin(annotation) is Annotated:
            actual_type, *meta = get_args(annotation)
            depends = next((m for m in meta if isinstance(m, DependsType)), None)

            if depends:
                default, annotation, status = depends, actual_type, "🔗 explicit"
                injected += 1
            elif isinstance(actual_type, ForwardRef):
                default, annotation, status = _create_lazy_depends(actual_type), object, "🔄 forwardRef"
                injected += 1
            elif actual_type in _registry:
                default, annotation, status = Depends(_registry[actual_type]), actual_type, "✨ injected"
                injected += 1

        elif isinstance(annotation, ForwardRef):
            default, annotation, status = _create_lazy_depends(annotation), object, "🔄 forwardRef"
            injected += 1

        elif annotation in _registry:
            default, status = Depends(_registry[annotation]), "✨ injected"
            injected += 1

        type_name = getattr(annotation, "__name__", str(annotation))
        _log(f"   ├─ {name}: {type_name} {status}")

        new_params.append(inspect.Parameter(
            name=name,
            kind=param.kind,
            default=default,
            annotation=annotation,
        ))

    func.__signature__ = inspect.Signature(
        parameters=new_params,
        return_annotation=sig.return_annotation,
    )

    _log(f"   ✅ Injected: {injected}/{len(new_params)} params")
    _log(f"{'─'*60}\n")

    return func


def Controller(prefix: str = "", tags: list[str] | None = None):
    """
    Mark a class as a controller (combines @Injectable with routing metadata).
    
    Args:
        prefix: URL prefix for all routes.
        tags: OpenAPI tags for documentation.
    
    Returns:
        Decorator function.
    """
    def decorator(cls: Type[T]) -> Type[T]:
        cls.__controller__ = True
        cls.__prefix__ = prefix
        cls.__tags__ = tags or []
        return Injectable(cls)
    return decorator


# -----------------------------------------------------------------------------
# Dependency Providers
# -----------------------------------------------------------------------------


def Provide(cls: Type[T]) -> DependsType:
    """
    Explicitly provide a dependency for injection.
    
    Use when type hint inference doesn't work.
    
    Args:
        cls: The injectable class to provide.
    
    Returns:
        FastAPI Depends() wrapper.
    
    Example:
        >>> @router.get("/example")
        >>> async def example(service = Provide(MyService)):
        >>>     return service.do_something()
    """
    provider = _registry.get(cls)
    if not provider:
        raise ValueError(f"{cls.__name__} is not @Injectable")
    return Depends(provider)


def get_service(cls: Type[T]) -> T:
    """
    Get a service instance programmatically.
    
    Useful for background tasks, CLI scripts, or anywhere outside
    FastAPI request context.
    
    Warning:
        Services with FastAPI dependencies (e.g., db sessions from Depends())
        cannot be created outside request context. For background workers:
        
        1. Create a separate db session for the worker
        2. Pass it to the service method directly
        
        Example for Celery/background tasks::
        
            async def background_task():
                async with async_session_maker() as session:
                    service = get_service(UserService)
                    await service.process_with_session(session)
    
    Args:
        cls: The injectable class to retrieve.
    
    Returns:
        Singleton instance of the service.
    
    Example:
        >>> service = get_service(UserService)
        >>> await service.process()
    """
    if cls not in _registry:
        raise ValueError(f"{cls.__name__} is not @Injectable")

    if cls in _instances:
        return _instances[cls]

    try:
        instance = _resolve_service_recursive(cls)
        _instances[cls] = instance
        _call_on_init(instance)  # Call lifecycle hook
        return instance
    except Exception as e:
        raise RuntimeError(
            f"Cannot create {cls.__name__} outside FastAPI context. "
            f"This service likely requires FastAPI dependencies.\n"
            f"Original error: {e}"
        ) from e


# -----------------------------------------------------------------------------
# Testing Utilities
# -----------------------------------------------------------------------------


class override:
    """
    Context manager to temporarily override a provider for testing.
    
    Example:
        >>> with override(UserService, mock_service):
        >>>     response = client.get("/users/1")
        >>>     assert response.status_code == 200
    """

    def __init__(self, cls: Type, mock_instance: Any) -> None:
        self.cls = cls
        self.mock_instance = mock_instance
        self._original_provider = None
        self._original_instance = None

    def __enter__(self):
        with _lock:
            self._original_provider = _registry.get(self.cls)
            self._original_instance = _instances.get(self.cls)

            def mock_provider(**kwargs):
                return self.mock_instance

            mock_provider.__signature__ = inspect.Signature(return_annotation=self.cls)
            mock_provider.__name__ = f"mock_{self.cls.__name__}"

            _registry[self.cls] = mock_provider
            _instances[self.cls] = self.mock_instance

        return self.mock_instance

    def __exit__(self, exc_type, exc_val, exc_tb):
        with _lock:
            if self._original_provider is not None:
                _registry[self.cls] = self._original_provider
            else:
                _registry.pop(self.cls, None)

            if self._original_instance is not None:
                _instances[self.cls] = self._original_instance
            else:
                _instances.pop(self.cls, None)

        return False


class test_container:
    """
    Context manager for complete test isolation.
    
    Creates a fresh registry and restores the original state after.
    
    Example:
        >>> with test_container():
        >>>     @Injectable
        >>>     class TestService:
        >>>         pass
        >>>     # TestService only exists inside this block
    """

    def __init__(self) -> None:
        self._original_registry = None
        self._original_instances = None

    def __enter__(self):
        with _lock:
            self._original_registry = _registry.copy()
            self._original_instances = _instances.copy()
            _registry.clear()
            _instances.clear()
        _get_cached_type_hints.cache_clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        with _lock:
            _registry.clear()
            _registry.update(self._original_registry)
            _instances.clear()
            _instances.update(self._original_instances)
        _get_cached_type_hints.cache_clear()
        return False


def clear_registry() -> None:
    """Clear all registrations and cached instances."""
    with _lock:
        _registry.clear()
        _instances.clear()
    _get_cached_type_hints.cache_clear()


# -----------------------------------------------------------------------------
# Lifecycle Management
# -----------------------------------------------------------------------------
#
# Why no init_all() function?
# ---------------------------
# on_init() is called automatically when a service is first accessed (lazy init).
# This happens either:
#   1. During the first HTTP request that uses the service
#   2. When get_service() is called in lifespan startup
#
# If you need eager initialization, call get_service() in your lifespan:
#
#     @asynccontextmanager
#     async def lifespan(app: FastAPI):
#         _ = get_service(CacheService)  # Triggers on_init()
#         yield
#         await async_shutdown_all()     # Triggers on_destroy()
#


def shutdown_all() -> None:
    """
    Call on_destroy() on all singleton instances.
    
    Use in application shutdown hooks.
    """
    with _lock:
        for cls, instance in list(_instances.items()):
            if hasattr(instance, "on_destroy") and callable(instance.on_destroy):
                try:
                    result = instance.on_destroy()
                    if inspect.iscoroutine(result):
                        import asyncio
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(result)
                        except RuntimeError:
                            asyncio.run(result)
                    _log(f"   🛑 {cls.__name__}.on_destroy() called")
                except Exception as e:
                    logger.warning(f"Error in {cls.__name__}.on_destroy(): {e}")


async def async_shutdown_all() -> None:
    """
    Async version of shutdown_all().
    
    Properly awaits async on_destroy() hooks.
    
    Example:
        >>> @asynccontextmanager
        >>> async def lifespan(app: FastAPI):
        >>>     yield
        >>>     await async_shutdown_all()
    """
    with _lock:
        for cls, instance in list(_instances.items()):
            if hasattr(instance, "on_destroy") and callable(instance.on_destroy):
                try:
                    result = instance.on_destroy()
                    if inspect.iscoroutine(result):
                        await result
                    _log(f"   🛑 {cls.__name__}.on_destroy() called")
                except Exception as e:
                    logger.warning(f"Error in {cls.__name__}.on_destroy(): {e}")