"""RuiPDF 启动入口：python main.py [文件.pdf]

（打包后的自检：RuiPDF.exe --selftest 报告文件.json，见 ruipdf/selftest.py）
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        from ruipdf.selftest import run
        sys.exit(run(sys.argv[2]))
    from ruipdf.mainwindow import main
    main()
