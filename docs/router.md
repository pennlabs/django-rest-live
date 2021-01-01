# RealtimeRouter

The `RealtimeRouter` object builds up mappings between DRF views and Django models, registers
signal handlers to get save and delete signals, and generates a channels `Consumer` subclass
to handle incoming websocket requests. Multiple `RealtimeRouter`s can be instantiated in the same application
to be handled by two separate consumers.

## API

### `router.register(view)`
Where `view` is a Generic APIView or ViewSet which inherits from 
[`RealtimeMixin`](mixin.md). Only one APIView can be registered for any given
model; a `RuntimeWarning` will be raised if yoou try to register
two views to the same router that have the same underlying model for their
`queryset`

### `as_consumer()`
Returns a subclass of `Consumer` that is set up to receive subscriptions and
send broadcasts 

