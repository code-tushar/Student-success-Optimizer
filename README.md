# Student Academic Success Optimizer

## Setup (once)
    python -m pip install streamlit pandas networkx plotly

## Run the website
    streamlit run app.py
(open http://localhost:8501 if the browser does not open by itself)

## Other commands
    python experiment.py                      # scheduler vs baseline experiment (console)
    python -m unittest discover -s tests -v   # 25 tests

## Deploy (Streamlit Community Cloud)
1. Upload this folder to a public GitHub repository.
2. Go to https://share.streamlit.io -> Create app -> choose the repository, branch `main`, main file `app.py` -> Deploy.
3. Open the app and click "Load sample data".
Note: the free cloud app may reset its SQLite database when it restarts.
