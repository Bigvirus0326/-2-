"""모드 메이커 실행 파일. 실행.bat 과 빌드 스크립트(build_release.py)가 이 파일을 쓴다.

프로그램 본체는 app_qt.py 에 있다 (Qt). 이 파일은 그곳의 main() 을 부를 뿐이다.
"""
import sys

from app_qt import main

if __name__ == "__main__":
    sys.exit(main())
