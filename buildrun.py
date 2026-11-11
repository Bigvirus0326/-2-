"""모드 / 빌드 탭의 ①검사 ②생성 ③빌드 ④게시 동작 (화면과 무관).

Tk 앱과 Qt 앱이 같이 쓴다. 화면 표시(메시지 상자, 로그 창)는 호출하는 쪽이 맡는다.
"""
import copy
import os
import shutil
import subprocess
import sys

import modgen as M


def validate(project):
    """(오류 목록, 경고 목록). 원본 프로젝트는 바꾸지 않는다."""
    return M.validate(copy.deepcopy(project))


def generate(project, settings, log=print):
    """프로젝트 파일을 출력 폴더에 만든다. 성공하면 만들어진 폴더 경로, 실패하면 예외."""
    errors, _ = validate(project)
    if errors:
        raise ValueError("검사에서 오류가 있습니다: " + "; ".join(errors[:3]))
    out = settings.get("out_dir") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(out, exist_ok=True)
    return M.generate(copy.deepcopy(project), out, copy.deepcopy(settings), log=log)


def check_build_prereqs(settings, publish):
    """빌드 전에 확인할 것. 문제가 있으면 사용자에게 보일 한 줄 설명, 없으면 None."""
    if not shutil.which("dotnet"):
        return ".NET SDK(dotnet)가 없습니다. https://dotnet.microsoft.com 에서 .NET SDK 9 이상을 설치하세요."
    if publish and not os.path.isfile(settings.get("godot_path", "")):
        return "pck를 만들려면 MegaDot 4.5.1 (mono) 실행 파일 경로가 필요합니다.\n'모드 / 빌드' 탭의 환경 설정에서 지정하세요."
    return None


def build_command(publish, sts2_path):
    cmd = ["dotnet", "publish" if publish else "build", "-nologo"]
    if sts2_path:
        cmd.append(f"-p:Sts2Path={sts2_path}")
    return cmd


def run_build(cmd, cwd, log):
    """dotnet 을 실행하고 출력 줄을 log 로 보낸다. 끝나면 종료 코드를 돌려준다 (오류는 log 로)."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE="ko", DOTNET_NOLOGO="1")
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             creationflags=flags, env=env)
        try:
            for raw in p.stdout:
                try:
                    line = raw.decode("utf-8")
                except UnicodeDecodeError:
                    line = raw.decode("cp949", errors="replace")
                if line.strip():
                    log(line)
        finally:
            p.stdout.close()
        return p.wait()
    except Exception as e:  # noqa: BLE001
        log(f"[오류] 실행 실패: {e}")
        return -1
