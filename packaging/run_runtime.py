"""PyInstaller entry wrapper — keep import path stable when frozen."""

from office_agent.__main__ import main

if __name__ == "__main__":
    main()
