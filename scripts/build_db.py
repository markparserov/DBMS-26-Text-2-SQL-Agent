#!/usr/bin/env python3
"""
Сборка SQLite из parquet- и xlsx-файлов в data/parquet/.
Результат: data/db/business.db

Использование:
    python scripts/build_db.py
    python scripts/build_db.py /path/to/data/folder
    python scripts/build_db.py -o data/db/custom.db
"""
import argparse
from pathlib import Path
import re
import sqlite3

import pandas as pd


def project_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    assert root.name != "scripts", "expected project root"
    return root


def data_dir(root: Path) -> Path:
    return root / "data" / "parquet"


def db_path(root: Path) -> Path:
    return root / "data" / "db" / "business.db"


def filename_to_table(name: str) -> str:
    """1_market_access.parquet -> market_access; 9_t_dict_municipal_districts.xlsx -> t_dict_municipal_districts."""
    stem = Path(name).stem
    return re.sub(r"^\d+_", "", stem)


def load_table(path: Path) -> "pd.DataFrame":
    """Загружает таблицу из .parquet или .xlsx."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, engine="openpyxl")
    raise ValueError(f"Не поддерживается формат: {suffix}")


def build_sqlite(
    data_dir_path: Path,
    db_path_out: Path,
) -> None:
    data_dir_path = Path(data_dir_path)
    db_path_out = Path(db_path_out)
    db_path_out.parent.mkdir(parents=True, exist_ok=True)

    parquet_files = sorted(data_dir_path.glob("*.parquet"))
    xlsx_files = sorted(data_dir_path.glob("*.xlsx")) + sorted(data_dir_path.glob("*.xls"))
    files = parquet_files + xlsx_files
    if not files:
        raise FileNotFoundError(
            f"В каталоге {data_dir_path} нет .parquet или .xlsx файлов. "
            "Положите их в data/parquet/ или укажите путь: python scripts/build_db.py /путь/к/папке"
        )

    with sqlite3.connect(db_path_out) as conn:
        for f in files:
            table = filename_to_table(f.name)
            df = load_table(f)
            df.to_sql(table, conn, index=False, if_exists="replace")
            print(f"  {f.name} -> таблица {table!r} ({len(df)} строк)")

    print(f"Готово: {db_path_out}")


def main() -> None:
    root = project_root()
    parser = argparse.ArgumentParser(description="Сборка SQLite из parquet/xlsx -> data/db/business.db")
    parser.add_argument("data_dir_path", nargs="?", default=None, type=Path, help="Папка с .parquet/.xlsx (по умолчанию data/parquet)")
    parser.add_argument("-o", "--output", default=None, type=Path, help="Путь к .db (по умолчанию data/db/business.db)")
    args = parser.parse_args()
    data_path = args.data_dir_path or data_dir(root)
    out_path = args.output or db_path(root)
    build_sqlite(data_path, out_path)


if __name__ == "__main__":
    main()
