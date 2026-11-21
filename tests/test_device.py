import unittest
from unittest import mock

from lmphone import access, device, proxy, service
from lmphone.executor import call, parse_screen
from lmphone.masking import Masker, Vault


def node(cls, bounds, children=(), **extra):
    left, top, right, bottom = bounds
    return {"className": cls, "boundsInScreen": {"left": left, "top": top, "right": right, "bottom": bottom},
            "children": list(children), **extra}


STATE = {
    "device_context": {"screen_bounds": {"width": 1080, "height": 2340}},
    "phone_state": {"currentApp": "Settings", "packageName": "com.android.settings", "isEditable": False, "focusedElement": None},
    "a11y_tree": node("android.widget.FrameLayout", (0, 0, 1080, 2340), [
        node("android.widget.TextView", (0, 100, 500, 200), text="Display", resourceId="com.x:id/title"),
        node("android.widget.Switch", (800, 300, 1000, 400), contentDescription="Dark mode", isCheckable=True, isChecked=True),
        node("android.widget.Button", (0, 3000, 100, 3100), text="Below the screen"),
        node("android.view.View", (0, 2000, 1080, 2340), resourceId="com.google.android.inputmethod.latin:id/keyboard",
             children=[node("android.widget.TextView", (0, 2000, 100, 2100), text="q")]),
        node("android.view.View", (0, 500, 100, 600)),
    ]),
}

# O texto que o Mobilerun entrega para essa árvore sem visão (filtro detalhado, formato indexado).
TEXT = """**Current Phone State:**
• **App:** Settings (com.android.settings)
• **Keyboard:** Hidden
• **Focused Element:** ''

Current Clickable UI elements:
'index. className: resourceId; checkedState, text - bounds(x1,y1,x2,y2)':
1. FrameLayout: "android.widget.FrameLayout" - (0,0,1080,2340)
2. TextView: "com.x:id/title", "Display" - (0,100,500,200)
3. Switch: "Dark mode" ; isChecked=True - (800,300,1000,400)
4. View: "android.view.View" - (0,500,100,600)"""


class ScreenTextTest(unittest.TestCase):
    def test_same_text_as_mobilerun(self):
        self.assertEqual(device.render(STATE, device.elements_of(STATE)), TEXT)

    def test_the_executor_reads_it(self):
        elements, _ = parse_screen(f"<device_state>\n{TEXT}\n</device_state>")
        self.assertEqual([(e.index, e.text, e.checked) for e in elements],
                         [(1, "", None), (2, "Display", None), (3, "Dark mode", True), (4, "", None)])
        self.assertEqual(elements[1].ids, ("com.x:id/title",))

    def test_focus_and_keyboard(self):
        state = {**STATE, "phone_state": {"packageName": "com.x", "isEditable": True, "focusedElement": {"text": "E-mail"}}}
        text = device.render(state, [])
        self.assertIn("• **App:** com.x\n• **Keyboard:** Visible\n• **Focused Element:** 'E-mail'", text)
        self.assertTrue(text.endswith("No UI elements found"))

    def test_offscreen_parent_stays_when_a_child_is_visible(self):
        tree = node("a.Root", (0, 0, 1080, 2340), [node("a.List", (0, 2400, 1080, 4000), [node("a.Row", (0, 2300, 1080, 2500), text="Row")])])
        self.assertEqual([e["text"] for e in device.elements_of({**STATE, "a11y_tree": tree})], ["a.Root", "a.List", "Row"])


class TapPointTest(unittest.TestCase):
    def elements(self, **cover):
        tree = node("a.Root", (0, 0, 1080, 2340), [
            node("a.Row", (0, 100, 1000, 300), text="Row", drawingOrder=1, windowId=7),
            node("a.Button", (400, 100, 1000, 300), text="Over", drawingOrder=2, windowId=7, isClickable=True, **cover),
        ])
        return device.elements_of({**STATE, "a11y_tree": tree})

    def test_centre_when_nothing_covers_it(self):
        self.assertEqual(device.point(self.elements(isVisibleToUser=False)[1]), (500, 200))

    def test_moves_off_a_clickable_sibling_drawn_above(self):
        self.assertEqual(device.point(self.elements()[1], 1080, 2340), (200, 200))

    def test_tap_by_index_goes_through_adb(self):
        phone = device.Device()
        phone.elements, phone.size = self.elements(), (1080, 2340)
        with mock.patch.object(device, "adb") as adb:
            self.assertIsNone(phone.act("click", {"index": "2"}))
            self.assertIn("No element with index 9", phone.act("click", {"index": "9"}))
        adb.assert_called_once_with("shell", "input", "tap", "200", "200")


class ActionTest(unittest.TestCase):
    def test_calls_written_by_the_executor_are_parsed_back(self):
        self.assertEqual(device.parse_call(call("type", text="a <b>\nc", clear="true")), ("type", {"text": "a <b>\nc", "clear": "true"}))
        self.assertEqual(device.parse_call("no call here"), (None, {}))

    def test_actions(self):
        phone = device.Device()
        with mock.patch.object(device, "adb") as adb, mock.patch.object(phone, "request") as request:
            _, params = device.parse_call(call("swipe", coordinate="[540, 1800]", coordinate2="[540, 800]", duration="1.0"))
            self.assertIsNone(phone.act("swipe", params))
            self.assertIsNone(phone.act("system_button", {"button": "enter"}))
            self.assertIsNone(phone.act("type", {"text": "olá", "clear": "true"}))
            self.assertEqual(phone.act("type_text", {}), "Unknown tool: type_text")
        self.assertEqual(adb.call_args_list, [mock.call("shell", "input", "swipe", "540", "1800", "540", "800", "1000"),
                                              mock.call("shell", "input", "keyevent", "66")])
        request.assert_called_once_with("/keyboard/input", {"base64_text": "b2zDoQ==", "clear": True})

    def test_typing_the_portal_could_not_verify_is_not_a_failure(self):
        phone = device.Device()
        with mock.patch.object(phone, "request", side_effect=RuntimeError("o Portal respondeu erro: input accepted via IME but could not be verified")):
            self.assertIsNone(phone.act("type", {"text": "x"}))
        with mock.patch.object(phone, "request", side_effect=RuntimeError("o Portal respondeu erro: no focused input")):
            self.assertIn("no focused input", phone.act("type", {"text": "x"}))

    def test_a_failed_action_is_reported_not_raised(self):
        with mock.patch.object(device, "adb", side_effect=RuntimeError("adb shell: device offline")):
            self.assertIn("device offline", device.Device().act("system_button", {"button": "back"}))


class CycleTest(unittest.TestCase):
    """O ciclo do serviço, com o aparelho e o executor trocados por registros."""

    def run_cycle(self, answers, errors=(), cancel_after=None, packages=()):
        self.messages, self.acts, errors, cancelled = [], [], list(errors), mock.Mock()
        self.access = mock.Mock(BankOpen=access.BankOpen, is_bank=access.is_bank)
        fake = mock.Mock(read=lambda: TEXT, act=None, package=None)
        packages = iter(packages)

        def read():
            fake.package = next(packages, fake.package or "com.android.settings")  # o último fica
            return TEXT
        cancelled.is_set.side_effect = lambda: cancel_after is not None and len(self.acts) >= cancel_after
        answers = iter(answers)

        def step(message, model, arrived):
            self.messages.append(message)
            return next(answers)

        def act(name, params):
            self.acts.append((name, params))
            return errors.pop(0) if errors else None

        fake.read, fake.act = read, act
        patches = [mock.patch.object(service, "device", fake), mock.patch.object(service, "access", self.access),
                   mock.patch.object(service, "AFTER_ACTION", 0), mock.patch.object(service, "STILL_GAP", 0),
                   mock.patch.object(proxy, "local_step", step),
                   mock.patch.object(proxy, "packages_at", 1e12),
                   *(mock.patch.object(proxy, name) for name in ("begin", "judge_task", "plan_ahead", "log"))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return service.run("task", "model", True, lambda line: None, cancelled)

    def test_acts_until_the_executor_completes(self):
        outcome = self.run_cycle([f"Tap.\n\n{call('click', index=3)}", f"Done.\n\n{call('complete', success='true', message='ok')}"])
        self.assertEqual(outcome, (True, "ok"))
        self.assertEqual(self.acts, [("click", {"index": "3"})])
        self.assertTrue(all(f"<device_state>\n{TEXT}\n</device_state>" in message for message in self.messages))

    def test_a_tool_error_reaches_the_executor_before_the_next_screen(self):
        self.run_cycle([f"Tap.\n\n{call('click', index=99)}", f"x\n\n{call('complete', success='false', message='no')}"],
                       errors=["Failed to click: No element with index 99"])
        self.assertNotIn("<error>", self.messages[0])
        self.assertIn("<error>Failed to click: No element with index 99</error>", self.messages[1].split("<device_state>")[0])

    def test_a_screen_in_motion_is_read_again_until_it_stops(self):
        frames = iter(["sliding 1", "sliding 2", TEXT, TEXT, "never read"])
        with mock.patch.object(service, "device", mock.Mock(read=lambda: next(frames))), mock.patch.object(service, "STILL_GAP", 0):
            self.assertEqual(service.read_screen(), TEXT)
        self.assertEqual(next(frames), "never read")

    def test_an_interrupted_task_stops_acting(self):
        tap = f"Tap.\n\n{call('click', index=3)}"
        self.assertIsNone(self.run_cycle([tap, tap, tap], cancel_after=1))
        self.assertEqual(len(self.acts), 1)


    def test_accessibility_is_on_during_the_task(self):
        self.run_cycle([f"Done.\n\n{call('complete', success='true', message='ok')}"])
        self.access.on.assert_called_once()

    def test_a_bank_in_front_at_the_start_stops_before_any_action(self):
        with mock.patch.object(service, "switch_on", lambda result: result.append("bank")):
            outcome = self.run_cycle([f"Tap.\n\n{call('click', index=3)}"])
        self.assertEqual(outcome, (False, service.BANK_MESSAGE))
        self.assertEqual(self.acts, [])

    def test_a_bank_that_shows_up_mid_task_turns_everything_off(self):
        tap = f"Tap.\n\n{call('click', index=3)}"
        outcome = self.run_cycle([tap, tap, tap], packages=["com.android.settings"] * 2 + ["br.com.intermedium"])  # duas leituras por passo (tela parada)
        self.assertEqual(outcome, (False, service.BANK_MESSAGE))
        self.assertEqual(len(self.acts), 1)
        self.access.off.assert_called_once()


class FakeShell:
    """O `adb shell` das chamadas de access.py, sobre um registro de ajustes e teclados."""

    def __init__(self, services="null", keyboard="com.samsung.android.honeyboard/.service.HoneyBoardService", front="com.android.settings"):
        self.settings = {"enabled_accessibility_services": services, "accessibility_enabled": "0" if services == "null" else "1",
                         "default_input_method": keyboard}
        self.enabled_imes, self.front = [keyboard], front

    def __call__(self, *args, timeout=15):
        if args[0].startswith("pm path"):
            return f"package:/data/app/{access.PORTAL}/base.apk"
        if args[0].startswith("dumpsys"):
            return f"topResumedActivity=ActivityRecord{{1 u0 {self.front}/.Main t9}}"
        if args[:2] == ("settings", "get"):
            return self.settings.get(args[3], "null")
        if args[:2] == ("settings", "put"):
            self.settings[args[3]] = args[4]
        elif args[:2] == ("settings", "delete"):
            self.settings.pop(args[3], None)
        elif args[:2] == ("ime", "list"):
            return "\n".join(self.enabled_imes)
        elif args[:2] == ("ime", "set"):
            self.settings["default_input_method"] = args[2]
        elif args[:2] == ("ime", "disable"):
            self.enabled_imes.remove(args[2])
        return ""

    def portal_keyboard_on(self):
        self.enabled_imes.append(access.KEYBOARD)
        self.settings["default_input_method"] = access.KEYBOARD


class AccessTest(unittest.TestCase):
    def use(self, shell):
        for patch in (mock.patch.object(access, "adb", shell),
                      mock.patch.object(access, "IME_FILE", self.enterContext(__import__("tempfile").TemporaryDirectory()) + "/ime.prev")):
            patch.start()
            self.addCleanup(patch.stop)
        return shell

    def test_on_and_off_leave_other_services_and_the_keyboard_as_they_were(self):
        other = "com.example/.Reader"
        shell = self.use(FakeShell(services=other))
        access.on()
        self.assertEqual(shell.settings["enabled_accessibility_services"], f"{other}:{access.SERVICE}")
        shell.portal_keyboard_on()  # o que device.keyboard faz
        access.off()
        self.assertEqual(shell.settings["enabled_accessibility_services"], other)
        self.assertEqual(shell.settings["accessibility_enabled"], "1")
        self.assertEqual(shell.settings["default_input_method"], "com.samsung.android.honeyboard/.service.HoneyBoardService")
        self.assertNotIn(access.KEYBOARD, shell.enabled_imes)

    def test_off_with_no_other_service_turns_accessibility_off(self):
        shell = self.use(FakeShell())
        access.on()
        self.assertEqual(shell.settings["accessibility_enabled"], "1")
        access.off()
        self.assertNotIn("enabled_accessibility_services", shell.settings)
        self.assertEqual(shell.settings["accessibility_enabled"], "0")
        self.assertFalse(access.is_on())

    def test_a_bank_in_front_is_refused(self):
        shell = self.use(FakeShell(front="br.com.intermedium"))
        with self.assertRaises(access.BankOpen):
            access.on()
        self.assertEqual(shell.settings["enabled_accessibility_services"], "null")

    def test_off_when_already_off_changes_nothing(self):
        shell = self.use(FakeShell())
        before = dict(shell.settings)
        access.off()
        self.assertEqual(shell.settings, before)

    def test_the_proxy_does_not_open_a_bank(self):
        with mock.patch.object(proxy, "packages", {"inter": "br.com.intermedium"}), mock.patch.object(proxy, "rivals", {}), \
             mock.patch.object(proxy, "log"), mock.patch.object(proxy.subprocess, "run") as run:
            proxy.packages_ready.set()
            self.assertFalse(proxy.launch("Inter"))
        run.assert_not_called()


class SameNameAppsTest(unittest.TestCase):
    APPS = [{"label": "Messages", "packageName": "com.google.messages"}, {"label": "Messages", "packageName": "com.samsung.messages"},
            {"label": "Clock", "packageName": "com.clock"}]

    def launch(self, name, default):
        patches = [mock.patch.object(proxy, name_, value) for name_, value in (("packages", {}), ("rivals", {}), ("packages_at", 0.0))]
        patches += [mock.patch.object(proxy, "apps", lambda: self.APPS), mock.patch.object(proxy, "log")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        proxy.load_packages()
        ran = mock.Mock(returncode=0, stdout=default + "\n", stderr="")
        with mock.patch.object(proxy.subprocess, "run", return_value=ran) as run:
            opened = proxy.launch(name)
        return opened, run.call_args[0][0]

    def test_the_default_sms_app_wins(self):
        opened, command = self.launch("Messages", "com.google.messages")
        self.assertTrue(opened)
        self.assertIn("com.google.messages", command)

    def test_otherwise_the_last_listed(self):
        self.assertIn("com.samsung.messages", self.launch("messages", "null")[1])

    def test_a_single_name_does_not_ask_the_phone(self):
        self.assertIn("com.clock", self.launch("Clock", "x")[1])


class SessionPerTaskTest(unittest.TestCase):
    def setUp(self):
        for name in ("TASK", "SESSION", "CACHE", "masker", "judged", "requests", "executor", "opened", "began"):
            patcher = mock.patch.object(proxy, name, getattr(proxy, name))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(proxy, "new_masker", lambda: Masker(Vault()))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fake_values_do_not_cross_tasks(self):
        proxy.begin("first task")
        first, session = proxy.masker, proxy.SESSION
        first.add_name("Arctos")
        proxy.executor = object()
        proxy.begin("second task", use_cache=False)
        self.assertIsNot(proxy.masker, first)
        self.assertNotEqual(proxy.SESSION, session)
        self.assertEqual(proxy.masker.mask("Arctos"), "Arctos")
        self.assertIsNone(proxy.executor)
        self.assertFalse(proxy.judged.is_set())
        self.assertEqual((proxy.TASK, proxy.CACHE), ("second task", False))

    def test_a_late_judgment_does_not_touch_the_next_task(self):
        proxy.begin("fala pro marcos que já saí")
        old = proxy.judged

        def slow(task, timeout):
            proxy.begin("open the clock")  # a tarefa anterior foi interrompida e outra começou
            return {"intencao": "acao", "entidades": [{"texto": "marcos", "tipo": "pessoa", "precisa_pesquisa": False}]}, "", 1.0

        with mock.patch.object(proxy.local_ai, "judge_request", slow), mock.patch.object(proxy, "log") as log:
            proxy.judge_task()
        self.assertTrue(old.is_set())
        self.assertFalse(proxy.judged.is_set())
        self.assertNotIn("marcos", proxy.masker.session.extra_names)  # (mascarar "marcos" o aprenderia pela regra)
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
