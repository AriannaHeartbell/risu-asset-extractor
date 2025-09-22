import { decodeRPack } from './rpack_bg.js';

const fileInput = document.getElementById('risumFileInput');
const resultsDiv = document.getElementById('results');
const statusDiv = document.getElementById('status');
const downloadAllBtn = document.getElementById('downloadAllBtn');
const structureContainer = document.getElementById('structureContainer');
const structureView = document.getElementById('structureView');
const downloadStructureBtn = document.getElementById('downloadStructureBtn');

fileInput.addEventListener('change', handleFileSelect);

/**
 * ... (getExtensionFromBytes 함수는 기존과 동일)
 */
function getExtensionFromBytes(uint8Array) {
    if (uint8Array.length < 12) return null;
    if (uint8Array[0] === 137 && uint8Array[1] === 80 && uint8Array[2] === 78 && uint8Array[3] === 71) return 'png';
    if (uint8Array[0] === 255 && uint8Array[1] === 216 && uint8Array[2] === 255) return 'jpg';
    if (uint8Array[0] === 71 && uint8Array[1] === 73 && uint8Array[2] === 70 && uint8Array[3] === 56) return 'gif';
    if (uint8Array[0] === 82 && uint8Array[1] === 73 && uint8Array[2] === 70 && uint8Array[3] === 70 &&
        uint8Array[8] === 87 && uint8Array[9] === 69 && uint8Array[10] === 80 && uint8Array[11] === 80) return 'webp';
    return null;
}

async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    resultsDiv.innerHTML = '';
    statusDiv.textContent = `'${file.name}' 파일 처리 중...`;
    statusDiv.className = '';
    downloadAllBtn.style.display = 'none';
    structureContainer.style.display = 'none';
    structureView.textContent = '';
    downloadStructureBtn.onclick = null;

    try {
        const arrayBuffer = await file.arrayBuffer();
        const view = new DataView(arrayBuffer);
        const uint8Array = new Uint8Array(arrayBuffer);
        let pos = 0;

        const readByte = () => { const byte = view.getUint8(pos); pos += 1; return byte; };
        const readLength = () => { const len = view.getUint32(pos, true); pos += 4; return len; };
        const readData = (len) => { const data = uint8Array.subarray(pos, pos + len); pos += len; return data; };

        if (readByte() !== 111) throw new Error('잘못된 매직 넘버입니다.');
        if (readByte() !== 0) throw new Error('지원하지 않는 버전입니다.');

        const mainLen = readLength();
        const mainDataPacked = readData(mainLen);
        const mainDataDecoded = await decodeRPack(mainDataPacked);
        const mainJsonText = new TextDecoder().decode(mainDataDecoded);
        const mainJson = JSON.parse(mainJsonText);
        const moduleInfo = mainJson.module;

        const formattedJson = JSON.stringify(mainJson, null, 2);
        structureView.textContent = formattedJson;
        structureContainer.style.display = 'block';

        downloadStructureBtn.onclick = () => {
            const blob = new Blob([formattedJson], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${file.name.replace(/\.[^/.]+$/, "")}_structure.json`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        };

        if (!moduleInfo.assets || moduleInfo.assets.length === 0) {
            statusDiv.textContent = '완료: 이 파일에는 추출할 에셋이 없습니다.';
            statusDiv.className = 'success';
            return;
        }

        statusDiv.textContent = `"${moduleInfo.name}" 모듈에서 ${moduleInfo.assets.length}개의 에셋을 발견했습니다.`;

        const zip = new JSZip();
        let assetIndex = 0;

        while (pos < uint8Array.length && assetIndex < moduleInfo.assets.length) {
            const marker = readByte();
            if (marker === 0) break;
            if (marker !== 1) continue;

            const assetLen = readLength();
            const assetDataPacked = readData(assetLen);
            const assetDataDecoded = await decodeRPack(assetDataPacked);
            const [assetId, _, assetType] = moduleInfo.assets[assetIndex];

            // --- ✨ 여기가 수정된 부분입니다 ✨ ---
            let filename = assetId;
            // ------------------------------------

            const knownExtensions = /\.(png|jpg|jpeg|gif|webp)$/i;

            if (!knownExtensions.test(assetId)) {
                let extension = null;
                if (assetType && typeof assetType === 'string' && assetType.length > 0 && assetType.length < 5) {
                    extension = assetType.split('/').pop();
                }
                if (!extension) {
                    extension = getExtensionFromBytes(assetDataDecoded);
                }
                if (extension) {
                    filename = `${filename}.${extension}`;
                }
            }

            zip.file(filename, assetDataDecoded);
            
            const blob = new Blob([assetDataDecoded], { type: assetType || 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.textContent = `다운로드: ${filename} (${(assetDataDecoded.length / 1024).toFixed(2)} KB)`;
            link.className = 'asset-link';
            resultsDiv.appendChild(link);
            
            assetIndex++;
        }

        if (assetIndex > 0) {
            downloadAllBtn.style.display = 'block';
            downloadAllBtn.onclick = () => {
                statusDiv.textContent = 'ZIP 파일 생성 중... 잠시만 기다려주세요.';
                zip.generateAsync({ type: 'blob' }).then(function(content) {
                    const url = URL.createObjectURL(content);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = `${moduleInfo.name}_assets.zip`;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                    statusDiv.textContent = 'ZIP 파일 다운로드가 시작되었습니다!';
                });
            };
        }

        statusDiv.className = 'success';
        statusDiv.textContent += ' (추출 완료!)';

    } catch (error) {
        statusDiv.textContent = `오류가 발생했습니다: ${error.message}`;
        statusDiv.className = 'error';
        console.error("추출 오류:", error);
    }
}