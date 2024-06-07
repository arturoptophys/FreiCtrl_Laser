from micropython import const
from supervisor import ticks_ms
try:
    from typing import Callable, Optional, Union
    from circuitpython_typing.io import ROValueIO
except ImportError:
    pass

_DEBOUNCED_STATE: int = const(0x01)
_UNSTABLE_STATE: int = const(0x02)
_CHANGED_STATE: int = const(0x04)

_TICKS_PER_SEC: int = const(1000)

_TICKS_PERIOD = const(1<<29)
_TICKS_MAX = const(_TICKS_PERIOD-1)
_TICKS_HALFPERIOD = const(_TICKS_PERIOD//2)

@micropython.native
def ticks_add(ticks, delta):
    "Add a delta to a base number of ticks, performing wraparound at 2**29ms."
    return (ticks + delta) % _TICKS_PERIOD

@micropython.native
def ticks_diff(ticks1, ticks2):
    "Compute the signed difference between two ticks values, assuming that they are within 2**28 ticks"
    diff = (ticks1 - ticks2) & _TICKS_MAX
    diff = ((diff + _TICKS_HALFPERIOD) & _TICKS_MAX) - _TICKS_HALFPERIOD
    return diff
@micropython.native
def ticks_less(ticks1, ticks2):
    "Return true if ticks1 is less than ticks2, assuming that they are within 2**28 ticks"
    return ticks_diff(ticks1, ticks2) < 0

@micropython.native
def ticks_tonow(ticks, delta):
    return ticks_less(ticks_add(ticks, delta), ticks_ms())


class Debouncer:
    """Debounce an input pin or an arbitrary predicate
    Modified from source to not have floats !"""
    def __init__(
        self,
        io_or_predicate: Union[ROValueIO, Callable[[], bool]],
        interval: int = 10,
    ) -> None:
        """Make an instance.
        :param DigitalInOut/function io_or_predicate: the DigitalIO or
                                                      function that returns a boolean to debounce
        :param float interval: bounce threshold in seconds (default is 0.010, i.e. 10 milliseconds)
        """
        self.state = 0x00
        self.pin = io_or_predicate
        if hasattr(io_or_predicate, "value"):
            self.function = lambda: io_or_predicate.value
        else:
            self.function = io_or_predicate
        if self.function():
            self._set_state(_DEBOUNCED_STATE | _UNSTABLE_STATE)
        self._last_bounce_ticks = 0
        self._last_duration_ticks = 0
        self._state_changed_ticks = 0

        # Could use the .interval setter, but pylint prefers that we explicitly
        # set the real underlying attribute:
        self._interval_ticks = int(interval)

    def _set_state(self, bits: int) -> None:
        self.state |= bits

    def _unset_state(self, bits: int) -> None:
        self.state &= ~bits

    def _toggle_state(self, bits: int) -> None:
        self.state ^= bits

    def _get_state(self, bits: int) -> bool:
        return (self.state & bits) != 0

    @micropython.native
    def update(self, new_state: Optional[int] = None) -> None:
        """Update the debouncer state. MUST be called frequently"""
        now_ticks = ticks_ms()
        self._unset_state(_CHANGED_STATE)
        if new_state is None:
            current_state = self.function()
        else:
            current_state = bool(new_state)
        if current_state != self._get_state(_UNSTABLE_STATE):
            self._last_bounce_ticks = now_ticks
            self._toggle_state(_UNSTABLE_STATE)
        else:
            if ticks_diff(now_ticks, self._last_bounce_ticks) >= self._interval_ticks:
                if current_state != self._get_state(_DEBOUNCED_STATE):
                    self._last_bounce_ticks = now_ticks
                    self._toggle_state(_DEBOUNCED_STATE)
                    self._set_state(_CHANGED_STATE)
                    self._last_duration_ticks = ticks_diff(
                        now_ticks, self._state_changed_ticks
                    )
                    self._state_changed_ticks = now_ticks

    @property
    def interval(self) -> int:
        """The debounce delay, in seconds"""
        return self._interval_ticks

    @interval.setter
    def interval(self, new_interval_s: int) -> None:
        self._interval_ticks = new_interval_s

    @property
    def value(self) -> bool:
        """Return the current debounced value."""
        return self._get_state(_DEBOUNCED_STATE)

    @property
    def rose(self) -> bool:
        """Return whether the debounced value went from low to high at the most recent update."""
        return self._get_state(_DEBOUNCED_STATE) and self._get_state(_CHANGED_STATE)

    @property
    def fell(self) -> bool:
        """Return whether the debounced value went from high to low at the most recent update."""
        return (not self._get_state(_DEBOUNCED_STATE)) and self._get_state(
            _CHANGED_STATE
        )

    @property
    def last_duration(self) -> int:
        """Return the number of seconds the state was stable prior to the most recent transition."""
        return self._last_duration_ticks

    @property
    def current_duration(self) -> int:
        """Return the number of seconds since the most recent transition."""
        return ticks_diff(ticks_ms(), self._state_changed_ticks)

def timed_function(f, *args, **kwargs):
    """Decorator to time a function"""
    myname = str(f).split(' ')[1]
    def new_func(*args, **kwargs):
        t = ticks_ms()
        result = f(*args, **kwargs)
        delta = ticks_diff(ticks_ms(), t)
        print(f'Function {myname} Time = {delta:6.3f}ms')
        return result
    return new_func
