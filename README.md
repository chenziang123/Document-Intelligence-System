前端：
cd frontend
npm install
npm run dev

后端：
cd src
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8001