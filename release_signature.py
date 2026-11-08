"""Detached RSA/SHA-256 signatures for Windows release ZIPs."""
import base64
import hashlib
import os
from pathlib import Path
import subprocess

from publisher_key import CERTIFICATE, THUMBPRINT


def _powershell(script, **values):
    exe = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-Command",
                             "$ErrorActionPreference='Stop'; " + script],
                            env={**os.environ, **values}, capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError("배포자 서명 처리 실패: " + result.stderr.strip())
    return result.stdout.strip()


def _digest(path):
    with open(path, "rb") as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode("ascii")


_HASH_ARGS = "[Convert]::FromBase64String($env:STS_HASH),[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1"


def verify(path, signature):
    if len(signature) != 384:
        raise ValueError("배포자 서명이 없거나 형식이 잘못되었습니다.")
    script = (
        "$c=[Security.Cryptography.X509Certificates.X509Certificate2]::new([Convert]::FromBase64String($env:STS_CERT));"
        "$k=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPublicKey($c);"
        "if (!$k.VerifyHash([Convert]::FromBase64String($env:STS_HASH),[Convert]::FromBase64String($env:STS_SIG),"
        "[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)){throw 'Invalid signature'}")
    _powershell(script, STS_CERT=CERTIFICATE,
                STS_SIG=base64.b64encode(signature).decode("ascii"), STS_HASH=_digest(path))


def sign(path):
    result = _powershell(
        "$store=[Security.Cryptography.X509Certificates.X509Store]::new('My','CurrentUser');$store.Open('ReadOnly');$c=$store.Certificates.Find('FindByThumbprint',$env:STS_ID,$false)[0];if(!$c){throw 'Publisher certificate not found'};"
        "$k=[Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($c);"
        "[Convert]::ToBase64String($k.SignHash(" + _HASH_ARGS + "))",
        STS_ID=THUMBPRINT, STS_HASH=_digest(path))
    signature = base64.b64decode(result, validate=True)
    verify(path, signature)
    dest = str(path) + ".sig"
    Path(dest).write_bytes(signature)
    return dest

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sign a release ZIP with the registered Windows publisher key.")
    parser.add_argument("zip", type=Path)
    args = parser.parse_args()
    print(sign(args.zip))
