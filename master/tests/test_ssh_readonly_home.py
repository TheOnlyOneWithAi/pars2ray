from pathlib import Path

from app.services import ssh_provision


def test_ssh_client_does_not_touch_home_ssh() -> None:
    source = Path(ssh_provision.__file__).read_text(encoding="utf-8")

    assert "Path.home()" not in source
    assert "save_host_keys(" not in source
    assert "load_host_keys(" not in source
    assert "known_hosts.parent.mkdir" not in source
