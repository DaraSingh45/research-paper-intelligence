"""Pipeline package: the reusable orchestration logic shared by Streamlit
(ad-hoc "START RESEARCH" runs) and Airflow (scheduled recurring runs).

Business logic lives here -- NOT inside airflow/dags/research_pipeline.py --
per the project rule that DAGs must only call reusable Python modules.
"""
