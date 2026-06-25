import os
import re
import io
import zipfile
import tarfile
import urllib.request
import platform
import subprocess
import shutil
import json
from introlix.config import CUDA_VERSION, LLAMA_CPP_VERSION, APP_PATH

def get_cuda_version():
    try:
        startupinfo = None
        if hasattr(subprocess, 'STARTUPINFO'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        output = subprocess.check_output(
            ['nvidia-smi'], 
            stderr=subprocess.DEVNULL, 
            startupinfo=startupinfo
        ).decode('utf-8', errors='ignore')
        
        match = re.search(r'CUDA Version:\s*(\d+\.\d+)', output)
        if match:
            return float(match.group(1))
            
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None
    return None

def user_hardware():
    os_name = platform.system().lower()
    arch = platform.machine().lower()

    if os_name == "darwin":
        if "arm64" in arch:
            return "macos-arm64"
        return "macos-x64"
    
    elif os_name == 'windows':
        is_windows_arm = 'arm64' in arch or 'aarch64' in arch

        if is_windows_arm:
            return "win-cpu-arm64"
        
        if shutil.which("nvidia-smi") is not None:
            cuda_version = get_cuda_version()
            
            if cuda_version is not None and cuda_version >= min(list(CUDA_VERSION.keys())):
                major_version = int(cuda_version)
                if major_version in CUDA_VERSION:
                    return f"win-cuda-{CUDA_VERSION[major_version]}-x64"
        
        if shutil.which("vulkaninfo") is not None:
            return "win-vulkan-x64"
    
        return "win-cpu-x64"
    
    elif os_name == 'linux':
        is_arm = 'arm64' in arch or 'aarch64' in arch

        if is_arm:
            if shutil.which("vulkaninfo") is not None:
                return "ubuntu-vulkan-arm64"
            return "ubuntu-arm64"
        else:
            if shutil.which("vulkaninfo") is not None or shutil.which("nvidia-smi") is not None:
                return "ubuntu-vulkan-x64"
            return "ubuntu-x64"

    return "unknown-cpu"

def download_llama_cpp_build():
    os.makedirs(APP_PATH, exist_ok=True)
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        hardware = user_hardware()
        os_name = platform.system().lower()

        if os_name == 'windows':
            url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_VERSION}/llama-{LLAMA_CPP_VERSION}-bin-{hardware}.zip"
        else:
            url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_VERSION}/llama-{LLAMA_CPP_VERSION}-bin-{hardware}.tar.gz"

        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            file_buffer = io.BytesIO()
            downloaded = 0
            
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                file_buffer.write(chunk)
                downloaded += len(chunk)
                
                progress = (downloaded / total_size) * 100 if total_size > 0 else 0
                yield json.dumps({
                    "status": "downloading",
                    "progress": round(progress, 2),
                    "downloaded_bytes": downloaded,
                    "total_bytes": total_size,
                    "message": f"Downloading {os.path.basename(url)}"
                }) + "\n"

        yield json.dumps({
            "status": "extracting",
            "progress": 100.0,
            "downloaded_bytes": total_size,
            "total_bytes": total_size,
            "message": "Extracting runtime binaries"
        }) + "\n"

        file_buffer.seek(0)
        if url.endswith('.zip'):
            with zipfile.ZipFile(file_buffer) as zip_ref:
                zip_ref.extractall(APP_PATH)
        elif url.endswith('.tar.gz') or url.endswith('.tgz'):
            with tarfile.open(fileobj=file_buffer, mode='r:gz') as tar_ref:
                tar_ref.extractall(APP_PATH)
        else:
            raise ValueError("Unsupported archive format. URL must end in .zip or .tar.gz")
        
        fix_permissions(APP_PATH)
        
        yield json.dumps({
            "status": "downloaded",
            "progress": 100.0,
            "downloaded_bytes": total_size,
            "total_bytes": total_size,
            "message": "Engine configuration complete"
        }) + "\n"

    except Exception as e:
        yield json.dumps({
            "status": "failed",
            "progress": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "message": f"Setup failed: {str(e)}"
        }) + "\n"
        return
    

def fix_permissions(target_dir: str):
    """Ensures binaries have executable flags on Unix-like operating systems."""
    if os.name != 'nt':  # If not Windows (Linux/Mac)
        for root, _, files in os.walk(target_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Check if it's one of the primary llama executables
                if 'llama-' in file or file == 'server':
                    try:
                        current_mode = os.stat(file_path).st_mode
                        # Add executable permission (+x)
                        os.chmod(file_path, current_mode | 0o111)
                    except OSError:
                        pass

if __name__ == "__main__":
    for update in download_llama_cpp_build():
        print(update)