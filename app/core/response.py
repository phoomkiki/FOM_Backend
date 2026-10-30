import json
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith('/api/v1/') or response.status_code >= 400:
            return response
        if response.status_code == 204:
            return JSONResponse(status_code=200, content={'message': 'ลบข้อมูลสำเร็จ', 'data': None})
        if 'application/json' not in response.headers.get('content-type', ''):
            return response
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.encode('utf-8') if isinstance(chunk, str) else chunk)
        try:
            payload = json.loads(b''.join(chunks))
        except (ValueError, TypeError):
            return response
        path, method = request.url.path, request.method.upper()
        if path in {'/api/v1/auth/line', '/api/v1/auth/admin'}:
            message, payload = 'เข้าสู่ระบบสำเร็จ', {'token': payload.get('access_token')} if isinstance(payload, dict) else None
        elif path.endswith('/auth/logout'):
            message = 'ออกจากระบบสำเร็จ'
        else:
            message = {'GET':'ดึงข้อมูลสำเร็จ','POST':'สร้างข้อมูลสำเร็จ','PUT':'บันทึกข้อมูลสำเร็จ','PATCH':'แก้ไขข้อมูลสำเร็จ','DELETE':'ลบข้อมูลสำเร็จ'}.get(method, 'ดำเนินการสำเร็จ')
        return JSONResponse(status_code=response.status_code, content={'message': message, 'data': payload}, headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-type'}})
