import time


class Logger:
    def __init__(self):
        pass

    def info(self, strInfo: str):
        print(time.strftime('%Y-%m-%d %H:%M:%S - INFO : ', time.localtime())+strInfo)

    def warning(self, strInfo: str):
        print("\033[31m{}\033[0m".format(time.strftime('%Y-%m-%d %H:%M:%S - WARNING : ', time.localtime()) + strInfo))

    def error(self,strInfo:str):
        print("\033[31m{}\033[0m".format(time.strftime('%Y-%m-%d %H:%M:%S - ERROR : ', time.localtime()) + strInfo))
        exit(-1)

    def processing(self,strInfo:str):
        print(time.strftime('%Y-%m-%d %H:%M:%S - PROCESSING : ', time.localtime())+strInfo)