from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from im_backend.api.core import get_current_user, get_file_service
from im_backend.application.services.file import FileService
from im_backend.application.services.file.service import FileAccessError, FileGoneError
from im_backend.infra.storage.files import FileTooLarge

router = APIRouter()


def file_error(exc):
    code = 500
    if isinstance(exc, FileAccessError):
        code = 403
    elif isinstance(exc, FileGoneError):
        code = 410
    elif isinstance(exc, FileTooLarge):
        code = 413
    elif isinstance(exc, KeyError):
        code = 404
    elif isinstance(exc, ValueError):
        code = 400
    elif isinstance(exc, PyMongoError):
        code = 503
    detail = '数据库不可用，请稍后重试' if code == 503 else ('文件操作失败，请稍后重试' if code == 500 else str(exc))
    return HTTPException(status_code=code, detail=detail)


@router.post('/files/upload', status_code=201)
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user),
                      service: FileService = Depends(get_file_service)):
    try:
        item = await run_in_threadpool(service.upload, user['user_id'], file.filename, file.content_type, file.file)
        return {'item': item}
    except (ValueError, KeyError, OSError, PyMongoError) as exc:
        raise file_error(exc) from exc
    finally:
        await file.close()


@router.get('/files')
def list_files(limit: int = Query(50, ge=1, le=100), before: str = '',
               user=Depends(get_current_user), service: FileService = Depends(get_file_service)):
    try:
        return service.list_owned(user['user_id'], limit, before)
    except (ValueError, KeyError, PyMongoError) as exc:
        raise file_error(exc) from exc


@router.get('/files/{file_id}/download')
def download_file(file_id: str, user=Depends(get_current_user), service: FileService = Depends(get_file_service)):
    try:
        record, path = service.download(file_id, user['user_id'])
        return FileResponse(path, filename=record['original_name'], media_type='application/octet-stream',
                            headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
    except (ValueError, KeyError, OSError, PyMongoError) as exc:
        raise file_error(exc) from exc


@router.delete('/files/{file_id}')
def delete_file(file_id: str, user=Depends(get_current_user), service: FileService = Depends(get_file_service)):
    try:
        return {'item': service.delete(file_id, user['user_id'])}
    except (ValueError, KeyError, OSError, PyMongoError) as exc:
        raise file_error(exc) from exc
