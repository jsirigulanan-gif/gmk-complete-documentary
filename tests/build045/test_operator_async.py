from queue import Queue

from gmk_operator.app import OperatorApp


class DeferredRoot:
    def __init__(self):
        self.callbacks = Queue()

    def after(self, delay, callback):
        self.callbacks.put(callback)


def test_background_failure_reaches_ui_with_original_error():
    app = OperatorApp.__new__(OperatorApp)
    app._busy = False
    app.root = DeferredRoot()
    app._set_busy = lambda *args: None
    app.log_line = lambda *args: None
    observed = []
    app._async_error = lambda label, error, detail: observed.append((label, error, detail))

    def fail():
        raise RuntimeError('source lookup failed')

    app._async('ค้นฟุตเทจ', fail)
    app.root.callbacks.get(timeout=3)()
    assert len(observed) == 1
    assert observed[0][0] == 'ค้นฟุตเทจ'
    assert str(observed[0][1]) == 'source lookup failed'
    assert 'RuntimeError: source lookup failed' in observed[0][2]
