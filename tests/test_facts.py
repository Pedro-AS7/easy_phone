import unittest

from lmphone import facts

OUT = ('Wifi is enabled\nWifi is connected to "Casa"\n#\n0\n1\n0\n3\n1\n#\n'
       'package=com.google.android.apps.youtube.music\n  state=PlaybackState {state=PLAYING(3)\n#\n'
       '[V] Connecting to AudioService\n[V] volume is 0 in range [0..15]\n[V] Connecting to AudioService\n'
       '[V] volume is 15 in range [0..15]\n13\n0\n0.85\n')


class LevelsTest(unittest.TestCase):
    """Volumes, brilho e letra lidos do sistema (docs/plano-tutor.md): explicam "tá mudo", "tela escura", "letra pequena"."""

    def test_rotation_and_screen_timeout(self):
        # 2026-11-19: a tela não mostra a rotação nem o tempo para apagar; o guia acabava "conferido" sem nada mudar.
        found = facts.parse(OUT + "1\n15000\n")
        self.assertEqual((found["auto_rotate"], found["screen_timeout"], found["font_scale"]), (True, 15, 0.85))
        self.assertIn("screen_timeout: 15 s", facts.describe(found))
        self.assertIs(facts.met({"screen_timeout": "up"}, {"screen_timeout": 60}, {"screen_timeout": 15}), True)
        self.assertEqual(facts.speak({"auto_rotate": False}), "giro automático da tela desligado")  # a palavra de quem reclama

    def test_parse(self):
        found = facts.parse(OUT)
        self.assertEqual((found["media_volume"], found["ring_volume"], found["brightness"]), (0, 100, 5))
        self.assertIs(found["auto_brightness"], False)
        self.assertEqual(found["font_scale"], 0.85)
        self.assertIn("media_volume: 0%", facts.describe(found))
        self.assertIn("font_scale: 0.85 (normal 1.0)", facts.describe(found))
        self.assertEqual(facts.parse(OUT.rsplit("#", 1)[0]).get("media_volume"), None)  # sem a parte nova, como antes

    def test_level_goal_and_speech(self):
        self.assertIs(facts.met({"media_volume": 70}, {"media_volume": 67}), True)
        self.assertIs(facts.met({"media_volume": 70}, {"media_volume": 40}), False)
        self.assertIsNone(facts.met({"brightness": True}, {"brightness": 40}))
        self.assertEqual(facts.speak({"brightness": 70}), "brilho da tela em 70%")


class ChangeTest(unittest.TestCase):
    """O objetivo pode ser uma mudança medida contra o começo da tarefa: "letra maior" é font_scale "up"."""

    def test_up_and_down_against_the_start(self):
        start = {"font_scale": 1.0, "media_volume": 40}
        self.assertIs(facts.met({"font_scale": "up"}, {"font_scale": 1.0}, start), False)
        self.assertIs(facts.met({"font_scale": "up"}, {"font_scale": 1.1}, start), True)
        self.assertIs(facts.met({"media_volume": "down"}, {"media_volume": 20}, start), True)
        self.assertIsNone(facts.met({"font_scale": "up"}, {"font_scale": 1.1}))  # sem o começo, não dá para saber
        self.assertEqual(facts.speak({"font_scale": "up"}), "letra maior")

    def test_what_changed(self):
        self.assertEqual(facts.changes({"font_scale": 1.0, "bluetooth": True}, {"font_scale": 2.0, "bluetooth": True}),
                         "font_scale: 1.0 → 2.0")
        self.assertEqual(facts.changes(None, {"font_scale": 2.0}), "")


class ToldTest(unittest.TestCase):
    def test_what_changed_in_a_level_is_said(self):
        from lmphone.facts import told
        self.assertEqual(told({"font_scale": 0.9, "brightness": 40}, {"font_scale": 1.0, "brightness": 40}), "letra maior")
        self.assertEqual(told({"ring_volume": 100, "brightness": 40}, {"ring_volume": 40, "brightness": 80}),
                         "volume do toque mais baixo e tela mais clara")
        self.assertEqual(told(None, {"font_scale": 1.0}), "")


if __name__ == "__main__":
    unittest.main()


class AudibleTest(unittest.TestCase):
    def test_a_volume_up_from_zero_only_counts_when_audible(self):
        # 2026-11-18: o toque foi de 0 a 1 de 15 (7%), e o "não faz barulho" foi dado por resolvido.
        self.assertFalse(facts.met({"ring_volume": "up"}, {"ring_volume": 7}, {"ring_volume": 0}))
        self.assertTrue(facts.met({"ring_volume": "up"}, {"ring_volume": 20}, {"ring_volume": 0}))
        self.assertTrue(facts.met({"brightness": "up"}, {"brightness": 7}, {"brightness": 0}))


class SoundModeTest(unittest.TestCase):
    def test_the_sound_mode_is_read_and_can_be_a_goal(self):
        out = 'Wifi is enabled\n#\n0\n0\n0\n3\n1\n1\n#\n#\nvolume is 0 in range [0..15]\nvolume is 0 in range [0..15]\n100\n0\n1.0\n'
        found = facts.parse(out)
        self.assertEqual(found["sound_mode"], "vibrar")
        self.assertFalse(facts.met({"sound_mode": "som"}, found))
        self.assertEqual(facts.speak({"sound_mode": "som"}), "modo de som em Som")
