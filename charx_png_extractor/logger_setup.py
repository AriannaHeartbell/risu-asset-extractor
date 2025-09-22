# logger_setup.py
import logging
import sys

def setup_logger():
    """애플리케이션의 로거를 설정합니다."""
    # 최상위 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # 로그 레벨 설정 (INFO 이상만 기록)

    # 이미 핸들러가 설정되어 있다면 중복 추가 방지
    if logger.hasHandlers():
        logger.handlers.clear()

    # 로그 형식 지정
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s] - %(message)s'
    )

    # 콘솔(터미널) 핸들러: 실시간 진행 상황 확인
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # 파일 핸들러: 모든 로그를 파일에 기록하여 보관
    file_handler = logging.FileHandler('extraction.log', mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logging.info("="*50)
    logging.info("로거가 성공적으로 설정되었습니다. 추출 로그 기록을 시작합니다.")
    logging.info("="*50)