import os
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from introlix.services.download_llm import download_hf_model
from introlix.services.download_llama_cpp_build import download_llama_cpp_build
from introlix.config import LLAMA_SERVER_PATH
from introlix.models import HFModelDownloadPayload

router = APIRouter(prefix="/services", tags=["services"])


@router.post("/download_model")
async def download_model(request: Request, payload: HFModelDownloadPayload):
    """
    Endpoint to download a Hugging Face model with progress updates.
    Accepts JSON body with { username, repo_id, quant }.
    """

    async def model_download():
        try:
            username = payload.username
            repo_id = payload.repo_id
            quant = payload.quant

            if not (username and repo_id):
                yield json.dumps(
                    {"status": "error", "message": "Missing username or repo_id"}
                ) + "\n"
                return

            for update in download_hf_model(
                username=username,
                repo_id=repo_id,
                branch_name="main",
                quant=quant,
            ):
                # Check if the client clicked cancel or disconnected
                if await request.is_disconnected():
                    yield json.dumps(
                        {
                            "status": "cancelled",
                            "progress": 0,
                            "downloaded_bytes": 0,
                            "total_bytes": 0,
                            "message": "Download cancelled by client",
                        }
                    ) + "\n"
                    break

                yield update

                # Some pause so FastAPI can detect if the user cancelled
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"Error during download: {e}")
            yield f'{{"status": "error", "message": "{str(e)}"}}\n'

    return StreamingResponse(model_download(), media_type="application/json")


@router.get("/llama_cpp_build_status")
async def llama_cpp_build_status():
    """
    Endpoint to check the status of the llama.cpp build.
    """
    if os.path.exists(LLAMA_SERVER_PATH):
        return {"status": "downloaded"}
    else:
        return {"status": "not_downloaded"}


@router.post("/download_llama_cpp_build")
async def download_llama_cpp(request: Request):
    """
    Endpoint to download and set up the llama.cpp runtime.
    """
    # check if llama_cpp is already downloaded and configured
    if os.path.exists(LLAMA_SERVER_PATH):
        return StreamingResponse(
            iter([json.dumps({"status": "already_downloaded"}) + "\n"]),
            media_type="application/json",
        )

    async def llama_cpp_download():
        for update in download_llama_cpp_build():
            # Check if the client clicked cancel or disconnected
            if await request.is_disconnected():
                yield json.dumps(
                    {
                        "status": "cancelled",
                        "progress": 0.0,
                        "downloaded_bytes": 0,
                        "total_bytes": 0,
                        "message": "Download cancelled by client",
                    }
                ) + "\n"
                break

            yield update
            await asyncio.sleep(0.01)

    return StreamingResponse(llama_cpp_download(), media_type="application/json")
