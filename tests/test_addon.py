"""The add-on itself, run against the fake bpy.

Everything else in this suite tests the GENERATED installer. This file tests
`lookdev_switcher.py` -- the part that stays behind in the user's .blend and is
registered again on every file load, every re-run of the text block, and every
Blender session. Its defects are lifecycle defects: not "does this compute the
right number" but "what is left over the second time".
"""

import types as pytypes
import unittest

import fakebpy
from _support import read_text


def a_run(bpy, name):
    """Execute the add-on the way Text Editor > Run Script does.

    A FRESH module every time, on purpose: that is exactly what Blender does,
    and it is the whole reason a second run cannot see the first one's state.
    register() is called separately so a test can choose the order.
    """
    module = pytypes.ModuleType(name)
    module.__file__ = "lookdev_switcher.py"
    source = read_text("lookdev_switcher.py")
    with fakebpy.installed(bpy):
        exec(compile(source, "lookdev_switcher.py", "exec"), module.__dict__)
    return module


class TheAutoCollectTimerDoesNotPileUp(unittest.TestCase):
    """Defect 16: every re-run of the text block added another timer.

    `register()` guards the timer with

        if not bpy.app.timers.is_registered(_auto_model_timer):

    and `is_registered` compares by IDENTITY. Running the block again gives
    Blender a fresh module with a new function object, which it does not
    recognise -- so it registered a second timer, then a third, each polling
    twice a second for ever. None of them could be stopped afterwards:
    `bpy.app.timers` cannot be enumerated, and `_teardown()` unregisters by
    identity too, so it only ever reached the newest one. Even opening an
    unrelated file left the earlier ones polling.

    The load_post handler had this right from the start -- it dedups by
    `__name__` across modules -- and that list is now also what a stale timer
    reads to find out it has been replaced.

    Mutation: timer-identity
    """

    def one_run(self):
        bpy = fakebpy.make()
        module = a_run(bpy, "lookdev_only")
        module.register()
        return bpy, module

    def two_runs(self):
        bpy = fakebpy.make()
        first = a_run(bpy, "lookdev_first")
        second = a_run(bpy, "lookdev_second")
        first.register()
        second.register()
        return bpy, first, second

    def test_one_run_registers_one_timer(self):
        bpy, _module = self.one_run()
        self.assertEqual(len(bpy.app.timers.registered), 1)

    def test_the_lone_timer_keeps_polling(self):
        # The guard must not retire the timer that IS in charge -- a fix that
        # switched the auto-collect off entirely would pass every test below.
        bpy, module = self.one_run()
        for _ in range(3):
            bpy.app.timers.tick()
        self.assertTrue(bpy.app.timers.is_registered(module._auto_model_timer),
                        "the timer in charge retired itself")

    def test_a_second_run_leaves_exactly_one_timer(self):
        bpy, _first, _second = self.two_runs()
        bpy.app.timers.tick()
        self.assertEqual(len(bpy.app.timers.registered), 1,
                         "a timer from an earlier run is still polling")

    def test_the_survivor_is_the_newest_run(self):
        bpy, first, second = self.two_runs()
        bpy.app.timers.tick()
        self.assertTrue(bpy.app.timers.is_registered(second._auto_model_timer),
                        "the run in charge lost its timer")
        self.assertFalse(bpy.app.timers.is_registered(first._auto_model_timer),
                         "the superseded run kept polling")

    def test_ten_runs_still_leave_one(self):
        # The defect grew without bound: one more timer every time the text
        # block was run, and a lookdev session runs it often.
        bpy = fakebpy.make()
        modules = [a_run(bpy, "lookdev_%d" % n) for n in range(10)]
        for module in modules:
            module.register()
        self.assertEqual(len(bpy.app.timers.registered), 10,
                         "wrong fixture: the runs did not each register one")
        bpy.app.timers.tick()
        self.assertEqual(len(bpy.app.timers.registered), 1)

    def test_the_load_post_handler_is_still_deduped(self):
        """The mechanism the retirement leans on.

        If this ever stops holding, the timers stop retiring -- silently. It
        is asserted here so the dependency is visible from the test that needs
        it, not only from the one that owns it.
        """
        bpy, _first, _second = self.two_runs()
        names = [getattr(h, "__name__", "") for h in bpy.app.handlers.load_post]
        self.assertEqual(names.count("_lookdev_load_post"), 1)

    def test_unregister_leaves_nothing_behind(self):
        bpy, module = self.one_run()
        module.unregister()
        self.assertEqual(bpy.app.timers.registered, [])
        self.assertEqual(bpy.app.handlers.load_post, [])


if __name__ == "__main__":
    unittest.main()
