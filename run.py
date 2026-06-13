"""
로컬 실행 런처 — IPv4/IPv6 듀얼스택 바인딩.

문제: `uvicorn --host 0.0.0.0`은 IPv4만 listen → Windows에서 `localhost`는
IPv6(::1)로 먼저 해석되므로 연결 실패 후 127.0.0.1로 폴백하며 ~2초 지연.

해결: AF_INET6 + IPV6_V6ONLY=0 듀얼스택 소켓 하나로 listen → `localhost`(::1)와
`127.0.0.1` 둘 다 즉시 연결.

사용법:
    python run.py            # 포트 3000 (기본)
    python run.py 8080       # 포트 지정

참고: --reload는 지원하지 않음 (듀얼스택 소켓 + 리로더 조합이 까다롭고,
      리로드 워커가 좀비 프로세스를 남기는 문제도 있어 제외).
      코드 자동 리로드가 필요하면 기존 방식 사용:
          python -m uvicorn app.main:app --port 3000 --reload
      (단, 이 경우 브라우저는 127.0.0.1 로 접속해야 빠름)
"""
import asyncio
import socket
import sys

import uvicorn

# Windows 콘솔(cp949) 출력 크래시 방지
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[union-attr]
except Exception:
    pass


def make_dual_stack_socket(port: int) -> socket.socket:
    """IPv4/IPv6 둘 다 수락하는 듀얼스택 listen 소켓."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    # IPv4-mapped 주소도 수락 (Windows/Linux 모두 듀얼스택)
    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    except (AttributeError, OSError):
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("::", port))
    sock.listen()
    sock.set_inheritable(True)
    return sock


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    sock = make_dual_stack_socket(port)
    print(f"==> 서버 실행 (IPv4/IPv6 듀얼스택, 포트 {port})")
    print(f"    권장 접속(IPv4): http://127.0.0.1:{port}   (localhost:{port} 도 동작)")
    config = uvicorn.Config("app.main:app", log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve(sockets=[sock]))


if __name__ == "__main__":
    main()
