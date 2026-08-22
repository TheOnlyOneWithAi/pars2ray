from pathlib import Path
import io
import secrets
import shlex
import tarfile


def run(c, cmd):
    # Commands are built from fixed installer strings; caller-controlled values are shell-quoted.
    _, out, err = c.exec_command(cmd, get_pty=True)  # nosec B601
    code = out.channel.recv_exit_status()
    _ = out.read()
    __ = err.read()
    if code != 0:
        raise RuntimeError(f"remote command failed ({code})")


def upload_tree(c, local, remote):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w:gz") as tf:
        tf.add(local, arcname=local.name)
    b.seek(0)
    s = c.open_sftp()
    try:
        remote_home = s.normalize(".")
        if not remote_home or not remote_home.startswith("/"):
            raise RuntimeError("could not determine remote home directory")
        tmp = f"{remote_home}/.pars2ray-upload-{secrets.token_hex(16)}.tgz"
        with s.file(tmp, "wb") as f:
            f.write(b.read())
    finally:
        s.close()

    command = (
        f"trap 'rm -f -- {shlex.quote(tmp)}' EXIT; "
        f"mkdir -p {shlex.quote(remote)} && "
        f"tar xzf {shlex.quote(tmp)} -C {shlex.quote(remote)} --strip-components=1"
    )
    run(c, command)
