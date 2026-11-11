"""Unit tests. Everything runs unprivileged inside a temporary directory:

    python3 -m unittest discover -s tests -v
"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "selfctl")
ORIGINAL_HOSTS = "# my hosts\n127.0.0.1 localhost\n::1 localhost\n10.0.0.5 nas facebook.com\n"


def load(root, config):
    os.environ["SELFCTL_ROOT"] = root
    os.environ["SELFCTL_CONFIG"] = config
    os.environ["SELFCTL_CLOCK_SYNCED"] = "0"
    os.environ["NO_COLOR"] = "1"
    loader = importlib.machinery.SourceFileLoader("selfctl_under_test", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="selfctl-test-")
        self.config = os.path.join(self.root, "config")
        os.makedirs(os.path.join(self.root, "etc"))
        with open(os.path.join(self.root, "etc/hosts"), "w") as fh:
            fh.write(ORIGINAL_HOSTS)
        self.m = load(self.root, self.config)

    def tearDown(self):
        for path in (self.m.HOSTS, self.m.STATE):       # locked when the tests run as root
            self.m.set_immutable(path, False)
        shutil.rmtree(self.root, ignore_errors=True)

    def overwrite(self, path, text):
        """Tamper with a file the way a determined user would."""
        self.m.set_immutable(path, False)
        with open(path, "w") as fh:
            fh.write(text)

    def hosts(self):
        with open(self.m.HOSTS) as fh:
            return fh.read()

    def start(self, seconds=600, domains=("example.com", "www.example.com")):
        return self.m.apply_request({"action": "start", "seconds": seconds,
                                     "domains": list(domains), "labels": ["test"]})


class Domains(Base):
    def test_accepts_plain_names_and_urls(self):
        n = self.m.normalize_domain
        self.assertEqual(n("Example.COM"), "example.com")
        self.assertEqual(n("https://www.reddit.com/r/linux?x=1#top"), "www.reddit.com")
        self.assertEqual(n("user:pw@host.example.org:8443/path"), "host.example.org")
        self.assertEqual(n("*.tiktok.com."), "tiktok.com")
        self.assertEqual(n("münchen.de"), "xn--mnchen-3ya.de")

    def test_rejects_dangerous_input(self):
        for bad in ("", "localhost", "com", "1.2.3.4", "a b.com", "evil.com\n1.1.1.1 good.com",
                    "foo..com", "-bad.com", "bad-.com", "x_y.com", "printer.local",
                    "a" * 64 + ".com", "ex ample.com", "foo.com;rm", "$(id).com", "::1"):
            with self.assertRaises(ValueError, msg=bad):
                self.m.normalize_domain(bad)

    def test_durations(self):
        p = self.m.parse_duration
        self.assertEqual(p("45"), 2700)
        self.assertEqual(p("90m"), 5400)
        self.assertEqual(p("1h30m"), 5400)
        self.assertEqual(p("1.5h"), 5400)
        self.assertEqual(p("2d"), 172800)
        self.assertEqual(p("30s"), 30)
        for bad in ("", "abc", "5x", "1s", "31d", "-5m", "1h foo"):
            with self.assertRaises(ValueError, msg=bad):
                p(bad)

    def test_expand_and_allowlist(self):
        e = self.m.expand_domains
        self.assertEqual(e(["a.com", "www.b.com"]), ["a.com", "www.a.com", "www.b.com"])
        self.assertEqual(e(["a.com", "m.a.com", "b.com"], allow=["a.com"]), ["b.com", "www.b.com"])


class Lists(Base):
    def test_builtin_lists_are_clean(self):
        lists = self.m.available_lists()
        self.assertIn("social", lists)
        self.assertGreaterEqual(len(lists), 8)
        for name, item in lists.items():
            self.assertEqual(item["problems"], [], name)
            self.assertGreater(len(item["domains"]), 5, name)
            self.assertTrue(item["title"], name)

    def test_custom_list_overrides_and_parses_hosts_syntax(self):
        d = self.m.user_lists_dir()
        os.makedirs(d)
        with open(os.path.join(d, "social.txt"), "w") as fh:
            fh.write("# title: Mine\n0.0.0.0 only.example.org  # comment\nnot a domain!\n")
        with open(os.path.join(d, "work.txt"), "w") as fh:
            fh.write("jira.example.org\n")
        lists = self.m.available_lists()
        self.assertEqual(lists["social"]["domains"], ["only.example.org"])
        self.assertEqual(lists["social"]["source"], "customised")
        self.assertEqual(lists["work"]["source"], "custom")
        self.assertTrue(lists["social"]["problems"])

    def test_resolve_targets_applies_allowlist(self):
        d = self.m.user_lists_dir()
        os.makedirs(d)
        with open(os.path.join(d, "allowlist.txt"), "w") as fh:
            fh.write("linkedin.com\n")
        names, extra, hosts = self.m.resolve_targets(["social", "foo.example.org"])
        self.assertEqual((names, extra), (["social"], ["foo.example.org"]))
        self.assertIn("www.facebook.com", hosts)
        self.assertIn("foo.example.org", hosts)
        self.assertFalse([h for h in hosts if h.endswith("linkedin.com")])


class Hosts(Base):
    def test_compose_then_strip_restores_original_bytes(self):
        composed = self.m.compose_hosts(ORIGINAL_HOSTS, ["facebook.com", "x.com"])
        self.assertIn("0.0.0.0 facebook.com\n:: facebook.com\n", composed)
        self.assertIn("#selfctl-disabled# 10.0.0.5 nas facebook.com", composed)
        self.assertEqual(self.m.strip_managed(composed), ORIGINAL_HOSTS)

    def test_compose_is_idempotent(self):
        once = self.m.compose_hosts(ORIGINAL_HOSTS, ["a.com"])
        self.assertEqual(self.m.compose_hosts(once, ["a.com"]), once)

    def test_truncated_block_is_cleaned(self):
        composed = self.m.compose_hosts(ORIGINAL_HOSTS, ["a.com", "b.com"])
        cut = composed.replace(self.m.END + "\n", "") + "1.2.3.4 keepme\n"
        self.assertEqual(self.m.strip_managed(cut), ORIGINAL_HOSTS + "1.2.3.4 keepme\n")


class Lifecycle(Base):
    def test_start_writes_block_and_state(self):
        state = self.start()
        self.assertIn("0.0.0.0 example.com", self.hosts())
        self.assertIn("0.0.0.0 dns.google", self.hosts())      # DoH bootstrap hosts
        self.assertEqual(self.m.load_state()["domains"], state["domains"])
        self.assertAlmostEqual(self.m.remaining_now(self.m.load_state()), 600, delta=2)

    def test_start_rejects_bad_requests(self):
        for req in ({"action": "start", "seconds": 600, "domains": []},
                    {"action": "start", "seconds": 1, "domains": ["a.com"]},
                    {"action": "start", "seconds": 10 ** 9, "domains": ["a.com"]},
                    {"action": "start", "seconds": 600, "domains": ["bad host"]},
                    {"action": "stop"}, {"action": "add", "domains": ["a.com"]},
                    {"action": "extend", "seconds": 60}):
            with self.assertRaises(SystemExit, msg=req):
                self.m.apply_request(req)
        self.assertEqual(self.hosts(), ORIGINAL_HOSTS)

    def test_cannot_start_twice_but_can_add_and_extend(self):
        self.start()
        with self.assertRaises(SystemExit):
            self.start()
        self.m.apply_request({"action": "add", "domains": ["more.example.org"], "labels": ["x"]})
        self.m.apply_request({"action": "extend", "seconds": 300})
        state = self.m.load_state()
        self.assertIn("more.example.org", state["domains"])
        self.assertIn("example.com", state["domains"])
        self.assertAlmostEqual(self.m.remaining_now(state), 900, delta=2)
        self.assertIn("0.0.0.0 more.example.org", self.hosts())

    def test_tampering_with_hosts_is_reverted(self):
        state = self.start()
        self.overwrite(self.m.HOSTS, ORIGINAL_HOSTS + "93.184.216.34 example.com\n")
        self.assertTrue(self.m.enforce_hosts(state["domains"]))
        text = self.hosts()
        self.assertIn("0.0.0.0 example.com", text)
        self.assertIn("#selfctl-disabled# 93.184.216.34 example.com", text)
        self.assertFalse(self.m.enforce_hosts(state["domains"]))

    def test_changing_the_wall_clock_does_not_end_the_block(self):
        state = self.start()
        real_time = self.m.time.time
        try:
            self.m.time.time = lambda: real_time() + 10 * 86400     # "date -s" into the future
            self.assertFalse(self.m.account(state))                 # clock is not NTP-synced
            os.environ["SELFCTL_CLOCK_SYNCED"] = "1"
            self.assertTrue(self.m.account(state))                  # a synced clock is trusted
        finally:
            self.m.time.time = real_time

    def test_downtime_is_not_credited_without_synced_clock(self):
        state = self.start()
        state["boot_id"] = "a-previous-boot"
        state["last_boottime"] = 5.0
        self.assertFalse(self.m.account(state))
        self.assertAlmostEqual(state["remaining"], 600, delta=1)

    def test_uptime_is_charged(self):
        state = self.start()
        state["last_boottime"] -= 601
        self.assertTrue(self.m.account(state))

    def test_finish_restores_everything(self):
        self.start()
        self.m.finish()
        self.assertEqual(self.hosts(), ORIGINAL_HOSTS)
        self.assertIsNone(self.m.load_state())

    def test_corrupt_state_is_not_a_block(self):
        os.makedirs(self.m.STATE_DIR)
        for junk in ("", "{", "[]", '{"domains": ["a.com"]}', '{"domains": "x", "duration": 5}'):
            self.overwrite(self.m.STATE, junk)
            self.assertIsNone(self.m.load_state(), junk)


class Daemon(Base):
    """Runs the real daemon loop as a subprocess inside the sandbox."""

    def spawn(self):
        env = dict(os.environ, SELFCTL_TICK="0.05")
        return subprocess.Popen([sys.executable, "-B", SCRIPT, "_daemon"], env=env)

    def wait_for(self, predicate, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_daemon_repairs_tampering_and_cleans_up_at_the_end(self):
        self.start(seconds=600)
        proc = self.spawn()
        try:
            # 1. wipe the block from hosts -> comes back
            self.overwrite(self.m.HOSTS, ORIGINAL_HOSTS)
            self.assertTrue(self.wait_for(lambda: "0.0.0.0 example.com" in self.hosts()))
            # 2. delete the state file -> rewritten from memory
            self.m.set_immutable(self.m.STATE, False)
            os.unlink(self.m.STATE)
            self.assertTrue(self.wait_for(lambda: self.m.load_state() is not None))
            # 3. edit the state to "almost over" -> ignored
            state = self.m.load_state()
            state["remaining"] = 0.01
            state["domains"] = ["example.com"]
            self.overwrite(self.m.STATE, json.dumps(state))
            self.assertTrue(self.wait_for(
                lambda: (self.m.load_state() or {}).get("remaining", 0) > 500
                and "www.example.com" in self.m.load_state()["domains"]))
            self.assertIsNone(proc.poll())
            # 4. add + extend through the front door -> picked up
            self.m.apply_request({"action": "add", "domains": ["late.example.org"]})
            self.assertTrue(self.wait_for(lambda: "0.0.0.0 late.example.org" in self.hosts()))
            # 5. SIGTERM -> exits non-zero (so systemd restarts it), block stays
            proc.terminate()
            self.assertEqual(proc.wait(timeout=10), 1)
            self.assertIn("0.0.0.0 example.com", self.hosts())
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_daemon_ends_the_block_when_time_is_up(self):
        self.start(seconds=600)
        state = self.m.load_state()
        state["last_boottime"] -= 598          # two seconds left
        self.m.save_state(state)
        proc = self.spawn()
        try:
            self.assertEqual(proc.wait(timeout=15), 0)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(self.hosts(), ORIGINAL_HOSTS)
        self.assertFalse(os.path.exists(self.m.STATE))

    def test_watchdog_enforces_when_daemon_is_dead(self):
        self.start(seconds=600)
        self.overwrite(self.m.HOSTS, ORIGINAL_HOSTS)
        self.assertEqual(self.m.cmd_watchdog(), 0)
        self.assertIn("0.0.0.0 example.com", self.hosts())


class CommandLine(Base):
    def run_cli(self, *args, **kw):
        env = dict(os.environ)
        return subprocess.run([sys.executable, "-B", SCRIPT] + list(args), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, **kw)

    def test_full_flow(self):
        r = self.run_cli("start", "10m", "social", "foo.example.org", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ACTIVE", r.stdout)
        self.assertIn("0.0.0.0 www.facebook.com", self.hosts())
        status = json.loads(self.run_cli("status", "--json").stdout)
        self.assertTrue(status["active"])
        self.assertIn("social", status["lists"])
        self.assertTrue(self.run_cli("status", "--short").stdout.startswith("🔒"))
        self.assertEqual(self.run_cli("add", "video").returncode, 0)
        self.assertIn("0.0.0.0 youtube.com", self.hosts())
        self.assertEqual(self.run_cli("extend", "5m").returncode, 0)
        self.assertNotEqual(self.run_cli("start", "5m", "news", "-y").returncode, 0)
        r = self.run_cli("stop")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no way to stop", r.stderr)

    def test_start_needs_confirmation(self):
        r = self.run_cli("start", "10m", "social", stdin=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.hosts(), ORIGINAL_HOSTS)

    def test_idle_outputs(self):
        self.assertFalse(json.loads(self.run_cli("status", "--json").stdout)["active"])
        self.assertEqual(self.run_cli("status", "--short").stdout, "")
        self.assertIn("social", self.run_cli("lists").stdout)
        self.assertEqual(self.run_cli("help").returncode, 0)
        self.assertNotEqual(self.run_cli("add", "social").returncode, 0)
        self.assertNotEqual(self.run_cli("start", "1h", "nosuchlist", "-y").returncode, 0)


if __name__ == "__main__":
    unittest.main()
