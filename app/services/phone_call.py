"""
Сервис звонков через FreePBX/AMI при событии «гость прибыл».
TTS: edge-tts → WAV 8kHz mono → SCP на FreePBX → AMI Originate.
"""
import asyncio
import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from asterisk.ami import AMIClient, SimpleAction
from paramiko import AutoAddPolicy, SSHClient

from app.database import SessionLocal
from app.models.setting import Setting
from app.services.settings import build_default_phone_notifications, normalize_phone_notifications

logger = logging.getLogger(__name__)

# В памяти: время последнего звонка (секунды с эпохи)
_last_call_time: float = 0


def _load_phone_notifications() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        record = db.query(Setting).filter(Setting.key == "phone_notifications").first()
        if not record or not record.value:
            return build_default_phone_notifications()
        return normalize_phone_notifications(json.loads(record.value))
    finally:
        db.close()


def _generate_tts_wav(text: str, out_path: Path) -> None:
    """TTS через edge-tts, конвертация в wav 8kHz mono для Asterisk."""
    import edge_tts
    from pydub import AudioSegment

    mp3_path = out_path.with_suffix(".mp3")

    async def _generate():
        communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
        await communicate.save(str(mp3_path))

    asyncio.run(_generate())

    audio = AudioSegment.from_mp3(str(mp3_path))
    audio = audio.set_frame_rate(8000).set_channels(1)
    audio.export(str(out_path), format="wav")
    try:
        mp3_path.unlink(missing_ok=True)
    except OSError:
        pass


def _scp_to_freepbx(local_path: Path, remote_path: str, config: Dict[str, Any]) -> None:
    """Копирует файл на FreePBX по scp. ssh_key — содержимое ключа из БД."""
    fp = config.get("freepbx") or {}
    ssh_key = fp.get("ssh_key") or ""
    ssh_host = fp.get("ssh_host")
    ssh_user = fp.get("ssh_user")

    if not ssh_host or not ssh_user:
        raise ValueError("freepbx: ssh_host и ssh_user обязательны")

    connect_kw: Dict[str, Any] = {
        "hostname": ssh_host,
        "username": ssh_user,
    }

    if ssh_key.strip():
        fd, key_path = tempfile.mkstemp(suffix=".key", dir=tempfile.gettempdir())
        try:
            os.write(fd, ssh_key.encode("utf-8"))
            os.close(fd)
            connect_kw["key_filename"] = key_path
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            ssh.connect(**connect_kw)
            sftp = ssh.open_sftp()
            sftp.put(str(local_path), remote_path)
            sftp.chmod(remote_path, 0o644)
            sftp.close()
            ssh.close()
        finally:
            try:
                Path(key_path).unlink(missing_ok=True)
            except OSError:
                pass
    else:
        raise ValueError("freepbx: ssh_key обязателен")


def _originate_call(config: Dict[str, Any], extension: str, playback_path: str) -> None:
    """AMI Originate: позвонить на extension и озвучить playback_path."""
    ami = config.get("ami") or {}
    host = ami.get("host")
    port = int(ami.get("port") or 5038)
    username = ami.get("username")
    password = ami.get("password")

    if not host or not username or not password:
        raise ValueError("ami: host, username и password обязательны")

    client = AMIClient(address=host, port=port)
    try:
        client.login(username=username, secret=password)
        # Local/EXT@from-internal/n — для ring groups и экстеншнов через dialplan FreePBX
        action = SimpleAction(
            "Originate",
            Channel=f"Local/{extension}@from-internal/n",
            Application="Playback",
            Data=playback_path,
            CallerID="TTS Caller <1200>",
            Timeout=30000,
        )
        future = client.send_action(action)
        response = future.response

        if response is None or response.is_error():
            msg = (
                response.keys.get("Message", "AMI failed") if response else "No response"
            )
            logger.warning("AMI Originate failed: %s (response: %s)", msg, response.keys if response else None)
            raise RuntimeError(msg)
    finally:
        try:
            client.logoff()
        except Exception:
            pass


def _do_call(
    extension: str,
    text: str,
    config: Dict[str, Any],
) -> None:
    """Выполнить звонок: TTS → SCP → Originate."""
    fp = config.get("freepbx") or {}
    sounds_path = (fp.get("sounds_path") or "").rstrip("/")
    if not sounds_path:
        raise ValueError("freepbx: sounds_path обязателен")

    file_id = str(uuid.uuid4())[:8]
    remote_filename = f"tts_{file_id}.wav"
    # SFTP chroot: для tts_upload путь /tmp = /home/tts_upload/tmp на сервере
    sftp_remote_path = f"/tmp/{remote_filename}"
    # Asterisk Playback — реальный путь на сервере (sounds_path)
    playback_path = f"{sounds_path}/{remote_filename}".replace(".wav", "")

    tmpdir = Path(tempfile.gettempdir())
    local_path = tmpdir / remote_filename

    try:
        _generate_tts_wav(text, local_path)
        _scp_to_freepbx(local_path, sftp_remote_path, config)
        _originate_call(config, extension, playback_path)
    finally:
        try:
            local_path.unlink(missing_ok=True)
        except OSError:
            pass


def _check_cooldown(config: Dict[str, Any]) -> bool:
    """Проверить, прошёл ли охладительный интервал."""
    global _last_call_time
    cooldown = max(1, int(config.get("call_cooldown_seconds") or 10))
    now = time.time()
    if now - _last_call_time < cooldown:
        return False
    return True


def _mark_call_done() -> None:
    global _last_call_time
    _last_call_time = time.time()


def maybe_call_on_guest_arrived(payload: Dict[str, Any]) -> None:
    """
    При событии entry_arrived: если phone_notifications включены и прошёл cooldown —
    позвонить и озвучить шаблон с подстановкой %GUESTNAME%.
    """
    try:
        config = _load_phone_notifications()
        if not config.get("enabled"):
            return

        if not _check_cooldown(config):
            logger.info("Звонок пропущен: не прошёл охладительный интервал")
            return

        change = payload.get("change") if isinstance(payload, dict) else None
        if not isinstance(change, dict):
            return
        entry = change.get("entry")
        if not isinstance(entry, dict):
            return

        guest_name = entry.get("name") or "Гость"
        extension = (config.get("extension") or "").strip()
        template = (config.get("arrival_template") or "").strip()
        if not extension or not template:
            logger.warning("phone_notifications: extension или arrival_template пусты")
            return

        text = template.replace("%GUESTNAME%", guest_name)

        _do_call(extension, text, config)
        _mark_call_done()
        logger.info("Звонок при приходе гостя инициирован: %s", guest_name)
    except Exception:
        logger.exception("Ошибка при инициации звонка при приходе гостя")
