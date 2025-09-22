import base64
import json
import png
import zipfile
from pathlib import Path
import shutil
import concurrent.futures
import logging

# 이 모듈의 로거 가져오기
logger = logging.getLogger(__name__)

# --- 파일 타입 자동 감지를 위한 함수 ---
def detect_image_extension(data: bytes) -> str:
    """파일 데이터의 첫 몇 바이트(매직 넘버)를 보고 확장자를 감지합니다."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xFF\xD8\xFF'): return '.jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return '.webp'
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'): return '.gif'
    return '.dat'

# --- 파일 저장을 위한 헬퍼 함수 ---
def save_asset_file(target_path: Path, source_path: Path = None, data: bytes = None) -> bool:
    """주어진 경로에 파일 데이터나 다른 파일을 복사하여 저장합니다."""
    try:
        if data:
            with open(target_path, 'wb') as f: f.write(data)
        elif source_path:
            shutil.copy(source_path, target_path)
        else:
            logger.warning("저장할 데이터나 원본 파일이 제공되지 않았습니다.")
            return False
        return True
    except Exception as e:
        logger.error(f"파일 저장 실패: {target_path.name}, 오류: {e}")
        return False

# --- 모드 1: CharX (ZIP) 파일에서 에셋 추출 ---
def extract_from_charx(file_path: Path):
    logger.info(f"'{file_path.name}' 파일을 CharX (ZIP) 형식으로 처리 시작...")
    output_folder = Path(f"{file_path.stem}_assets")
    output_folder.mkdir(exist_ok=True)
    temp_folder = Path(f"{file_path.stem}_temp_extraction")

    try:
        with zipfile.ZipFile(file_path, 'r') as archive:
            archive.extractall(path=temp_folder)
        logger.info(f"아카이브 내용을 임시 폴더 '{temp_folder.name}'에 추출했습니다.")

        card_json_path = temp_folder / 'card.json'
        if not card_json_path.is_file():
            logger.warning("'card.json'을 찾을 수 없습니다. 'assets' 폴더 내용만 복사합니다.")
            asset_src_folder = temp_folder / 'assets'
            if asset_src_folder.is_dir():
                shutil.copytree(asset_src_folder, output_folder, dirs_exist_ok=True)
                logger.info(f"'assets' 폴더 내용을 '{output_folder}'에 복사했습니다.")
            else:
                 logger.warning("'assets' 폴더를 찾지 못했습니다.")
            return

        with open(card_json_path, 'r', encoding='utf-8') as f:
            char_data = json.load(f)
        logger.info("'card.json' 파일을 읽어 에셋 정보를 확인합니다.")

        assets_info = char_data.get('data', {}).get('assets', [])
        if not assets_info:
            logger.warning("'card.json'에서 에셋 정보를 찾지 못했습니다.")
            return

        logger.info("JSON 정보를 기반으로 에셋 파일명을 변경하여 동시에 저장합니다.")
        tasks = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for asset_info in assets_info:
                uri, name, ext = asset_info.get('uri'), asset_info.get('name'), asset_info.get('ext')
                if not (uri and name): continue

                source_relative_path = Path(uri.replace('embeded://', '').replace('embed://', ''))
                source_full_path = temp_folder / source_relative_path
                
                if source_full_path.is_file():
                    # ✨ 여기가 수정된 부분입니다.
                    final_name = name
                    if ext and not name.lower().endswith(f'.{ext.lower()}'):
                        final_name = f"{name}.{ext}"

                    target_path = output_folder / final_name
                    tasks.append(executor.submit(save_asset_file, target_path, source_path=source_full_path))
                else:
                    logger.warning(f"원본 파일을 찾을 수 없습니다: {source_full_path}")
            
            results = [future.result() for future in concurrent.futures.as_completed(tasks)]
        
        saved_count = sum(1 for r in results if r)
        logger.info(f"총 {saved_count}개의 에셋을 '{output_folder}' 폴더에 성공적으로 저장했습니다.")

    except Exception as e:
        logger.error(f"ZIP 처리 중 심각한 오류 발생: {e}", exc_info=True)
    finally:
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
            logger.info(f"임시 폴더 '{temp_folder.name}'를 삭제했습니다.")

# --- 모드 2: PNG 카드 파일에서 에셋 추출 ---
def extract_all_data_from_png_chunks(file_path: Path) -> dict:
    main_data_str, assets = None, {}
    try:
        reader = png.Reader(filename=str(file_path))
        for chunk_type, chunk_data in reader.chunks():
            if chunk_type == b'tEXt':
                key, _, value = chunk_data.partition(b'\x00')
                key_str = key.decode('utf-8', errors='ignore')
                value_str = value.decode('utf-8', errors='ignore')
                
                if key_str.startswith('chara-ext-asset_'):
                    try:
                        asset_index = int(key_str.replace('chara-ext-asset_', '').replace(':', ''))
                        assets[asset_index] = base64.b64decode(value_str)
                    except (ValueError, IndexError):
                        logger.warning(f"잘못된 에셋 키 형식 '{key_str}'을 건너뜁니다.")
                elif key_str in ['chara', 'ccv3']:
                    main_data_str = value_str
    except Exception as e:
        logger.error(f"PNG 청크 스캔 중 오류: {e}", exc_info=True)
    
    logger.info(f"PNG 스캔 완료: 메인 데이터 {'발견' if main_data_str else '미발견'}, 에셋 {len(assets)}개 발견.")
    return {'main_data': main_data_str, 'assets': assets}

def save_assets_from_png(file_path: Path, asset_dict: dict, char_data: dict = None):
    if not asset_dict:
        logger.warning("추출할 PNG 에셋이 없습니다.")
        return
        
    output_folder = Path(f"{file_path.stem}_assets")
    output_folder.mkdir(exist_ok=True)
    logger.info(f"PNG 에셋을 '{output_folder}' 폴더에 동시에 저장합니다.")
    
    found_indices, tasks = set(), []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        if char_data:
            data_section = char_data.get('data', {})
            # v3, v2 구조의 에셋 정보를 순회하며 파일명 찾기
            asset_list = data_section.get('assets', []) # v3
            risu_ext = data_section.get('extensions', {}).get('risuai', {}) # v2
            asset_list.extend(risu_ext.get('additionalAssets', []))
            asset_list.extend(risu_ext.get('emotions', []))

            for item in asset_list:
                try:
                    # 구조에 따라 정보 추출 방식 통일
                    if isinstance(item, dict): # v3
                        uri, name, ext = item.get('uri'), item.get('name'), item.get('ext')
                    elif isinstance(item, list) and len(item) >= 2: # v2
                        name, uri, ext = Path(item[0]).stem, item[1], item[2] if len(item) > 2 else 'dat'
                    else: continue
                    
                    if uri and uri.startswith('__asset:'):
                        asset_index = int(uri.split(':')[-1])
                        if asset_index in asset_dict:
                            # ✨ 여기가 수정된 부분입니다.
                            file_name = name
                            if ext and not name.lower().endswith(f'.{ext.lower()}'):
                                file_name = f"{name}.{ext}"
                            
                            target_path = output_folder / file_name
                            tasks.append(executor.submit(save_asset_file, target_path, data=asset_dict[asset_index]))
                            found_indices.add(asset_index)
                except (ValueError, IndexError, TypeError): continue

        # 파일명을 찾지 못한 나머지 에셋 처리
        remaining_assets = {i: d for i, d in asset_dict.items() if i not in found_indices}
        if remaining_assets:
            if char_data: logger.info("JSON에 없는 나머지 에셋들을 기본 이름으로 저장합니다.")
            for index, data in remaining_assets.items():
                ext = detect_image_extension(data).lstrip('.')
                target_path = output_folder / f"asset_{index}.{ext}"
                tasks.append(executor.submit(save_asset_file, target_path, data=data))
        
        results = [future.result() for future in concurrent.futures.as_completed(tasks)]

    saved_count = sum(1 for r in results if r)
    logger.info(f"총 {saved_count}개의 PNG 에셋 파일을 저장했습니다.")

def extract_from_png_card(file_path: Path):
    logger.info(f"'{file_path.name}' 파일을 PNG 카드 형식으로 처리 시작...")
    extracted_data = extract_all_data_from_png_chunks(file_path)
    main_data_string, asset_dict = extracted_data['main_data'], extracted_data['assets']

    if not asset_dict and not main_data_string:
         logger.warning("이 파일에는 추출할 RisuAI 데이터나 에셋이 없는 것 같습니다.")
         return
    
    char_data = None
    if main_data_string:
        try:
            if not main_data_string.startswith('rcc||'):
                char_data = json.loads(base64.b64decode(main_data_string).decode('utf-8'))
            else:
                logger.warning("메인 데이터가 암호화되어 있어 파일명을 읽을 수 없습니다.")
        except Exception as e:
            logger.error(f"PNG 메인 데이터 파싱 중 오류 발생: {e}")

    save_assets_from_png(file_path, asset_dict, char_data)


# --- 메인 실행 로직 (UI에서 호출할 진입점) ---
def process_file(file_path_str: str) -> Path | None:
    """
    파일 경로를 받아 적절한 추출 함수를 호출하고,
    성공 시 결과 폴더 경로를 반환하고 실패 시 None을 반환합니다.
    """
    file_path = Path(file_path_str)
    output_folder = Path(f"{file_path.stem}_assets") # 결과 폴더 경로 미리 정의

    if not file_path.is_file():
        logger.error(f"오류: 파일을 찾을 수 없습니다 -> {file_path}")
        return None

    try:
        # 파일 타입 확인
        with open(file_path, 'rb') as f:
            is_png = f.read(8) == b'\x89PNG\r\n\x1a\n'
        
        if is_png:
             extract_from_png_card(file_path)
        elif zipfile.is_zipfile(file_path):
            extract_from_charx(file_path)
        else:
            logger.error("지원하지 않는 파일 형식입니다. '.png' 또는 '.charx' 파일을 입력해주세요.")
            return None

        # 성공적으로 끝나면 폴더 경로를 반환
        return output_folder

    except Exception as e:
        logger.error(f"파일을 처리하는 중 최상위 오류 발생: {e}", exc_info=True)
        return None # 오류 발생 시 None 반환