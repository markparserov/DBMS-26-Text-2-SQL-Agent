Положите сюда .parquet или .xlsx файлы, затем выполните из корня проекта:

  conda activate sql_agent
  pip install openpyxl   # только для .xlsx
  python scripts/build_db.py

Будет создана база data/db/business.db.

Имя файла → имя таблицы (префикс с цифрой опционален):
  1_market_access.parquet     -> market_access
  9_t_dict_municipal_districts.xlsx -> t_dict_municipal_districts

Если файлы лежат в другой папке:
  python scripts/build_db.py /путь/к/папке
