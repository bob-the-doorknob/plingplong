"""Python startup hook for the offline collector, including spawned interpreters."""
import os

if os.environ.get("BR_TRACE") == "1":
    import trace_events
    trace_events.start()

if os.environ.get("BR_PREDICATES") == "1":
    import trace_predicates
    trace_predicates.start()
