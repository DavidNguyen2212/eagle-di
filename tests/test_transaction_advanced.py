"""
Advanced Tests for Transactional + Injectable Integration
==========================================================

Tests the integration of @Transactional with @Injectable DI framework,
covering real-world scenarios like:
- Transactional services with DI
- Transaction propagation across service layers
- Error handling and rollback scenarios
- Concurrent operations
- Performance tests

Run with: pytest tests/test_transaction_advanced.py -v
"""

import asyncio
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.eagle_di import (
    Injectable,
    get_service,
    test_container,
    override,
    clear_registry,
)
from app.core.transaction import (
    Transactional,
    Propagation,
    Isolation,
    TransactionContext,
    TransactionTestContext,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def isolate_tests():
    """Each test runs in isolated DI container."""
    with test_container():
        yield


class MockAsyncSession:
    """Mock SQLAlchemy AsyncSession."""
    
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
        savepoint = MockSavepoint()
        self._savepoints.append(savepoint)
        return savepoint


class MockSavepoint:
    """Mock savepoint for NESTED propagation."""
    
    def __init__(self):
        self.committed = False
        self.rolled_back = False
    
    async def commit(self):
        self.committed = True
    
    async def rollback(self):
        self.rolled_back = True


class MockDatabaseProvider:
    """Mock DatabaseProvider that tracks all operations."""
    
    def __init__(self):
        self.sessions = []
        self._isolation_levels = []
        self.transaction_count = 0
        self.savepoint_count = 0
    
    def session_maker(self):
        session = MockAsyncSession()
        self.sessions.append(session)
        return session
    
    @asynccontextmanager
    async def transaction(self, isolation_level=None):
        self._isolation_levels.append(isolation_level)
        self.transaction_count += 1
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
        self.savepoint_count += 1
        savepoint = await session.begin_nested()
        try:
            yield session
            await savepoint.commit()
        except Exception:
            await savepoint.rollback()
            raise


@pytest.fixture
def mock_db():
    """Fixture providing a mock DatabaseProvider."""
    return MockDatabaseProvider()


# =============================================================================
# Test: @Injectable + @Transactional Integration
# =============================================================================


class TestInjectableTransactionalIntegration:
    """Tests combining @Injectable and @Transactional decorators."""
    
    @pytest.mark.asyncio
    async def test_injectable_service_with_transactional(self, mock_db):
        """@Injectable services work with @Transactional."""
        
        @Injectable
        class UserRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional
            async def create(self, name: str, db=None):
                db.add({"name": name})
                return {"id": 1, "name": name}
        
        repo = get_service(UserRepository)
        user = await repo.create("John")
        
        assert user == {"id": 1, "name": "John"}
        assert len(mock_db.sessions) == 1
        assert mock_db.sessions[0].committed is True
    
    @pytest.mark.asyncio
    async def test_nested_injectable_services(self, mock_db):
        """Nested @Injectable services share transaction correctly."""
        
        @Injectable
        class AuditRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def log(self, action: str, db=None):
                db.add({"audit": action})
                return True
        
        @Injectable
        class UserRepository:
            def __init__(self, audit: AuditRepository):
                self._db = mock_db
                self.audit = audit
            
            @Transactional
            async def create(self, name: str, db=None):
                db.add({"user": name})
                await self.audit.log(f"Created user: {name}", db=db)
                return {"name": name}
        
        repo = get_service(UserRepository)
        user = await repo.create("Jane")
        
        assert user == {"name": "Jane"}
        # Only 1 transaction created (shared)
        assert len(mock_db.sessions) == 1
        session = mock_db.sessions[0]
        assert {"user": "Jane"} in session.items_added
        assert {"audit": "Created user: Jane"} in session.items_added
    
    @pytest.mark.asyncio
    async def test_singleton_behavior_with_transactions(self, mock_db):
        """@Injectable singleton creates only one instance."""
        
        instance_count = []
        
        @Injectable
        class CountingService:
            def __init__(self):
                instance_count.append(1)
                self._db = mock_db
            
            @Transactional
            async def do_work(self, db=None):
                return "done"
        
        # Get service multiple times
        s1 = get_service(CountingService)
        s2 = get_service(CountingService)
        s3 = get_service(CountingService)
        
        assert s1 is s2 is s3
        assert len(instance_count) == 1  # Only instantiated once
        
        # Call transactional method
        await s1.do_work()
        await s2.do_work()
        
        assert len(mock_db.sessions) == 2  # Two transactions


# =============================================================================
# Test: Multi-Layer Transaction Propagation
# =============================================================================


class TestMultiLayerTransactionPropagation:
    """Tests transaction propagation across multiple service layers."""
    
    @pytest.mark.asyncio
    async def test_three_layer_propagation(self, mock_db):
        """Transaction propagates through Controller -> Service -> Repository."""
        
        @Injectable
        class ProductRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def save(self, product: dict, db=None):
                db.add({"product": product})
                return {**product, "id": 1}
        
        @Injectable
        class InventoryService:
            def __init__(self, repo: ProductRepository):
                self._db = mock_db
                self.repo = repo
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def add_stock(self, product: dict, quantity: int, db=None):
                saved = await self.repo.save(product, db=db)
                db.add({"inventory": {"product_id": saved["id"], "qty": quantity}})
                return saved
        
        @Injectable
        class ProductController:
            def __init__(self, inventory: InventoryService):
                self._db = mock_db
                self.inventory = inventory
            
            @Transactional
            async def create_product(self, name: str, quantity: int, db=None):
                product = await self.inventory.add_stock(
                    {"name": name}, quantity, db=db
                )
                db.add({"log": f"Product {name} created"})
                return product
        
        controller = get_service(ProductController)
        result = await controller.create_product("Widget", 100)
        
        assert result == {"name": "Widget", "id": 1}
        # Single transaction for all 3 layers
        assert len(mock_db.sessions) == 1
        session = mock_db.sessions[0]
        assert {"product": {"name": "Widget"}} in session.items_added
        assert {"inventory": {"product_id": 1, "qty": 100}} in session.items_added
        assert {"log": "Product Widget created"} in session.items_added
    
    @pytest.mark.asyncio
    async def test_mixed_propagation_modes(self, mock_db):
        """Different propagation modes work together correctly."""
        
        audit_logs = []
        
        @Injectable
        class AuditService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def log(self, message: str, db=None):
                audit_logs.append(message)
                db.add({"audit": message})
                return True
        
        @Injectable
        class PaymentService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.NESTED)
            async def process_payment(self, amount: float, should_fail: bool, db=None):
                db.add({"payment": amount})
                if should_fail:
                    raise ValueError("Payment declined")
                return True
        
        @Injectable
        class OrderService:
            def __init__(self, audit: AuditService, payment: PaymentService):
                self._db = mock_db
                self.audit = audit
                self.payment = payment
            
            @Transactional
            async def create_order(self, amount: float, payment_fails: bool, db=None):
                await self.audit.log("Order started")  # REQUIRES_NEW
                db.add({"order": amount})
                
                try:
                    await self.payment.process_payment(amount, payment_fails, db=db)  # NESTED
                except ValueError:
                    await self.audit.log("Payment failed")  # REQUIRES_NEW
                    db.add({"order_status": "payment_failed"})
                    return {"status": "payment_failed"}
                
                await self.audit.log("Order completed")  # REQUIRES_NEW
                return {"status": "completed", "amount": amount}
        
        order_service = get_service(OrderService)
        
        # Test failed payment
        result = await order_service.create_order(99.99, payment_fails=True)
        
        assert result == {"status": "payment_failed"}
        assert "Order started" in audit_logs
        assert "Payment failed" in audit_logs
        
        # Main transaction + 2 audit transactions
        assert mock_db.transaction_count == 3
        # 1 savepoint for NESTED payment
        assert mock_db.savepoint_count == 1


# =============================================================================
# Test: Error Handling and Rollback Scenarios
# =============================================================================


class TestTransactionErrorHandling:
    """Tests error handling and rollback in various scenarios."""
    
    @pytest.mark.asyncio
    async def test_rollback_propagates_through_layers(self, mock_db):
        """Exception in inner layer rolls back entire transaction."""
        
        @Injectable
        class FailingRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def will_fail(self, db=None):
                db.add({"before_fail": True})
                raise ValueError("Database constraint violation")
        
        @Injectable
        class ServiceWrapper:
            def __init__(self, repo: FailingRepository):
                self._db = mock_db
                self.repo = repo
            
            @Transactional
            async def do_work(self, db=None):
                db.add({"wrapper": True})
                await self.repo.will_fail(db=db)
                db.add({"after_fail": True})
                return "should not reach"
        
        service = get_service(ServiceWrapper)
        
        with pytest.raises(ValueError, match="constraint violation"):
            await service.do_work()
        
        # Transaction rolled back
        assert mock_db.sessions[0].rolled_back is True
    
    @pytest.mark.asyncio
    async def test_partial_failure_with_nested(self, mock_db):
        """NESTED propagation allows partial failure recovery."""
        
        @Injectable
        class BatchProcessor:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.NESTED)
            async def process_item(self, item: dict, db=None):
                db.add({"item": item["id"]})
                if item.get("should_fail"):
                    raise ValueError(f"Item {item['id']} failed")
                return True
        
        @Injectable
        class BatchService:
            def __init__(self, processor: BatchProcessor):
                self._db = mock_db
                self.processor = processor
            
            @Transactional
            async def process_batch(self, items: list, db=None):
                results = []
                for item in items:
                    try:
                        await self.processor.process_item(item, db=db)
                        results.append({"id": item["id"], "ok": True})
                    except ValueError:
                        results.append({"id": item["id"], "ok": False})
                
                db.add({"batch_results": results})
                return results
        
        service = get_service(BatchService)
        
        items = [
            {"id": 1},
            {"id": 2, "should_fail": True},
            {"id": 3},
            {"id": 4, "should_fail": True},
            {"id": 5},
        ]
        
        results = await service.process_batch(items)
        
        assert results == [
            {"id": 1, "ok": True},
            {"id": 2, "ok": False},
            {"id": 3, "ok": True},
            {"id": 4, "ok": False},
            {"id": 5, "ok": True},
        ]
        
        # Main transaction committed
        assert mock_db.sessions[0].committed is True
        # Savepoints: 5 total, 2 rolled back
        assert mock_db.savepoint_count == 5
    
    @pytest.mark.asyncio
    async def test_custom_rollback_rules(self, mock_db):
        """Custom rollback_for and no_rollback_for work correctly."""
        
        class BusinessLogicError(Exception):
            pass
        
        class ValidationError(Exception):
            pass
        
        @Injectable
        class RuleService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(
                rollback_for=(ValueError, TypeError),
                no_rollback_for=(BusinessLogicError,)
            )
            async def process(self, error_type: str, db=None):
                db.add({"processed": True})
                
                if error_type == "value":
                    raise ValueError("Value error")
                elif error_type == "business":
                    raise BusinessLogicError("Business logic error")
                elif error_type == "validation":
                    raise ValidationError("Validation error")
                
                return "success"
        
        service = get_service(RuleService)
        
        # BusinessLogicError should NOT rollback
        result = await service.process("business")
        assert result is None  # Returns None per implementation
        assert mock_db.sessions[0].rolled_back is False
        
        # ValueError should rollback
        with pytest.raises(ValueError):
            await service.process("value")
        assert mock_db.sessions[1].rolled_back is True


# =============================================================================
# Test: Concurrent Operations
# =============================================================================


class TestConcurrentTransactions:
    """Tests concurrent transaction handling."""
    
    @pytest.mark.asyncio
    async def test_concurrent_transactions_are_isolated(self, mock_db):
        """Multiple concurrent transactions are isolated."""
        
        @Injectable
        class ConcurrentService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional
            async def process(self, task_id: int, delay: float, db=None):
                db.add({"task_start": task_id})
                await asyncio.sleep(delay)
                db.add({"task_end": task_id})
                return task_id
        
        service = get_service(ConcurrentService)
        
        # Run 5 concurrent transactions
        tasks = [
            service.process(i, 0.1) for i in range(5)
        ]
        results = await asyncio.gather(*tasks)
        
        assert sorted(results) == [0, 1, 2, 3, 4]
        # Each task has its own session
        assert len(mock_db.sessions) == 5
        # All committed
        assert all(s.committed for s in mock_db.sessions)
    
    @pytest.mark.asyncio
    async def test_concurrent_with_shared_parent(self, mock_db):
        """Concurrent NESTED transactions share parent correctly."""
        
        @Injectable
        class WorkerService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.NESTED)
            async def do_work(self, worker_id: int, db=None):
                db.add({"worker": worker_id})
                await asyncio.sleep(0.05)
                return worker_id
        
        @Injectable
        class CoordinatorService:
            def __init__(self, worker: WorkerService):
                self._db = mock_db
                self.worker = worker
            
            @Transactional
            async def coordinate(self, worker_count: int, db=None):
                db.add({"coordinator": "started"})
                
                # Run workers concurrently with shared parent session
                tasks = [
                    self.worker.do_work(i, db=db) 
                    for i in range(worker_count)
                ]
                results = await asyncio.gather(*tasks)
                
                db.add({"coordinator": "finished"})
                return results
        
        coordinator = get_service(CoordinatorService)
        results = await coordinator.coordinate(3)
        
        assert sorted(results) == [0, 1, 2]
        # Single parent transaction
        assert len(mock_db.sessions) == 1
        # 3 savepoints for workers
        assert mock_db.savepoint_count == 3


# =============================================================================
# Test: Transaction Timeout Scenarios
# =============================================================================


class TestTransactionTimeouts:
    """Tests timeout behavior with @Injectable services."""
    
    @pytest.mark.asyncio
    async def test_timeout_with_injectable_service(self, mock_db):
        """Timeout works correctly with @Injectable services."""
        
        @Injectable
        class SlowService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(timeout=1)
            async def slow_operation(self, db=None):
                db.add({"started": True})
                await asyncio.sleep(2)
                db.add({"finished": True})
                return "done"
        
        service = get_service(SlowService)
        
        with pytest.raises(TimeoutError, match="timeout after 1s"):
            await service.slow_operation()
    
    @pytest.mark.asyncio
    async def test_timeout_in_nested_service(self, mock_db):
        """Timeout in NESTED propagation works correctly with parent transaction."""
        
        @Injectable
        class SlowInnerService:
            def __init__(self):
                self._db = mock_db
            
            # NESTED with timeout works because it wraps the savepoint operation
            @Transactional(propagation=Propagation.NESTED, timeout=1)
            async def slow_inner(self, db=None):
                await asyncio.sleep(2)
                return "done"
        
        @Injectable
        class OuterService:
            def __init__(self, inner: SlowInnerService):
                self._db = mock_db
                self.inner = inner
            
            @Transactional
            async def outer_operation(self, db=None):
                db.add({"outer": True})
                return await self.inner.slow_inner(db=db)
        
        service = get_service(OuterService)
        
        with pytest.raises(TimeoutError, match="timeout after 1s"):
            await service.outer_operation()


# =============================================================================
# Test: Override with Mocks
# =============================================================================


class TestTransactionalMocking:
    """Tests mocking transactional services using override()."""
    
    @pytest.mark.asyncio
    async def test_override_transactional_service(self, mock_db):
        """Can override @Transactional service with mock."""
        
        @Injectable
        class RealPaymentService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional
            async def charge(self, amount: float, db=None):
                # Real implementation would call payment gateway
                db.add({"charge": amount})
                return {"success": True, "transaction_id": "real_123"}
        
        @Injectable
        class OrderService:
            def __init__(self, payment: RealPaymentService):
                self._db = mock_db
                self.payment = payment
            
            @Transactional
            async def create_order(self, amount: float, db=None):
                db.add({"order": amount})
                result = await self.payment.charge(amount)
                return {"order_id": 1, "payment": result}
        
        # Create mock payment service
        mock_payment = MagicMock()
        mock_payment.charge = AsyncMock(
            return_value={"success": True, "transaction_id": "mock_456"}
        )
        
        with override(RealPaymentService, mock_payment):
            order_service = get_service(OrderService)
            result = await order_service.create_order(50.00)
        
        assert result["payment"]["transaction_id"] == "mock_456"
        mock_payment.charge.assert_called_once_with(50.00)


# =============================================================================
# Test: Lifecycle Hooks with Transactions
# =============================================================================


class TestLifecycleHooksWithTransactions:
    """Tests on_init lifecycle hooks with transactional services."""
    
    def test_on_init_called_for_transactional_service(self, mock_db):
        """on_init is called when @Transactional service is instantiated."""
        
        init_called = []
        
        @Injectable
        class ServiceWithInit:
            def __init__(self):
                self._db = mock_db
            
            def on_init(self):
                init_called.append(True)
            
            @Transactional
            async def do_work(self, db=None):
                return "done"
        
        service = get_service(ServiceWithInit)
        
        assert len(init_called) == 1
        assert isinstance(service, ServiceWithInit)
    
    @pytest.mark.asyncio
    async def test_transactional_method_after_on_init(self, mock_db):
        """@Transactional methods work after on_init completes."""
        
        config_loaded = []
        
        @Injectable
        class ConfigurableService:
            def __init__(self):
                self._db = mock_db
                self.config = None
            
            def on_init(self):
                self.config = {"setting": "value"}
                config_loaded.append(True)
            
            @Transactional
            async def get_config(self, db=None):
                db.add({"accessed_config": True})
                return self.config
        
        service = get_service(ConfigurableService)
        result = await service.get_config()
        
        assert result == {"setting": "value"}
        assert len(config_loaded) == 1


# =============================================================================
# Test: Complex Real-World Scenario
# =============================================================================


class TestComplexRealWorldScenario:
    """Tests a complete real-world e-commerce scenario."""
    
    @pytest.mark.asyncio
    async def test_ecommerce_checkout_flow(self, mock_db):
        """Complete checkout flow with multiple services."""
        
        events = []
        
        @Injectable
        class EventBus:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def publish(self, event: str, db=None):
                events.append(event)
                db.add({"event": event})
                return True
        
        @Injectable
        class InventoryRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def reserve(self, product_id: int, quantity: int, db=None):
                db.add({"reserve": {"product_id": product_id, "qty": quantity}})
                return True
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def release(self, product_id: int, quantity: int, db=None):
                db.add({"release": {"product_id": product_id, "qty": quantity}})
                return True
        
        @Injectable
        class PaymentGateway:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.NESTED)
            async def charge(self, amount: float, should_fail: bool, db=None):
                db.add({"payment_attempt": amount})
                if should_fail:
                    raise ValueError("Payment declined")
                db.add({"payment_success": amount})
                return {"transaction_id": "tx_123"}
        
        @Injectable
        class OrderRepository:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def create(self, order_data: dict, db=None):
                db.add({"order": order_data})
                return {"id": 1, **order_data}
        
        @Injectable
        class CheckoutService:
            def __init__(
                self,
                events: EventBus,
                inventory: InventoryRepository,
                payment: PaymentGateway,
                orders: OrderRepository,
            ):
                self._db = mock_db
                self.events = events
                self.inventory = inventory
                self.payment = payment
                self.orders = orders
            
            @Transactional
            async def checkout(
                self,
                product_id: int,
                quantity: int,
                amount: float,
                payment_fails: bool,
                db=None
            ):
                # Publish start event (separate transaction)
                await self.events.publish("checkout_started")
                
                # Reserve inventory
                await self.inventory.reserve(product_id, quantity, db=db)
                
                # Process payment (NESTED - can fail and recover)
                try:
                    payment_result = await self.payment.charge(amount, payment_fails, db=db)
                except ValueError:
                    # Release inventory on payment failure
                    await self.inventory.release(product_id, quantity, db=db)
                    await self.events.publish("checkout_failed")
                    return {"status": "failed", "reason": "payment_declined"}
                
                # Create order
                order = await self.orders.create({
                    "product_id": product_id,
                    "quantity": quantity,
                    "amount": amount,
                    "payment_id": payment_result["transaction_id"],
                }, db=db)
                
                await self.events.publish("checkout_completed")
                return {"status": "completed", "order": order}
        
        checkout_service = get_service(CheckoutService)
        
        # Test successful checkout
        result = await checkout_service.checkout(
            product_id=42,
            quantity=2,
            amount=99.99,
            payment_fails=False
        )
        
        assert result["status"] == "completed"
        assert result["order"]["product_id"] == 42
        assert "checkout_started" in events
        assert "checkout_completed" in events
        
        # Reset for next test
        mock_db.sessions.clear()
        mock_db.transaction_count = 0
        mock_db.savepoint_count = 0
        events.clear()
        
        # Test failed payment
        result = await checkout_service.checkout(
            product_id=42,
            quantity=2,
            amount=99.99,
            payment_fails=True
        )
        
        assert result["status"] == "failed"
        assert result["reason"] == "payment_declined"
        assert "checkout_started" in events
        assert "checkout_failed" in events


# =============================================================================
# Test: Performance Benchmarks
# =============================================================================


class TestTransactionPerformance:
    """Performance tests for transactional operations."""
    
    @pytest.mark.asyncio
    async def test_many_sequential_transactions(self, mock_db):
        """Test performance with many sequential transactions."""
        
        @Injectable
        class FastService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional
            async def quick_op(self, i: int, db=None):
                db.add({"op": i})
                return i
        
        service = get_service(FastService)
        
        import time
        start = time.perf_counter()
        
        results = []
        for i in range(100):
            result = await service.quick_op(i)
            results.append(result)
        
        elapsed = time.perf_counter() - start
        
        assert len(results) == 100
        assert len(mock_db.sessions) == 100
        # Should complete in reasonable time (< 1 second for mocks)
        assert elapsed < 1.0
    
    @pytest.mark.asyncio
    async def test_deeply_nested_propagation(self, mock_db):
        """Test deeply nested transaction propagation."""
        
        @Injectable
        class DeepService:
            def __init__(self):
                self._db = mock_db
            
            @Transactional(propagation=Propagation.MANDATORY)
            async def level(self, depth: int, current: int, db=None):
                db.add({"level": current})
                if current < depth:
                    return await self.level(depth, current + 1, db=db)
                return current
        
        @Injectable
        class RootService:
            def __init__(self, deep: DeepService):
                self._db = mock_db
                self.deep = deep
            
            @Transactional
            async def start(self, depth: int, db=None):
                return await self.deep.level(depth, 1, db=db)
        
        root = get_service(RootService)
        result = await root.start(10)
        
        assert result == 10
        # Single transaction, 10 levels deep
        assert len(mock_db.sessions) == 1
        session = mock_db.sessions[0]
        # All 10 levels recorded
        for i in range(1, 11):
            assert {"level": i} in session.items_added
