1. Create Environment, for dependency and python version management
```
conda create -n still_with_you python=3.10
```

2. Activate Environment

```
conda activate still_with_you
```

3. Install dependencies
```
python -m pip install -r requirements.txt
```

4. Run backend in seperate terminal
```
cd backend
python app.py
```

5. Run frontend in seperate terminal
```
cd frontend
python frontend.py
```

6. Open frontend app in browser
```
http://127.0.0.1:7890/
```