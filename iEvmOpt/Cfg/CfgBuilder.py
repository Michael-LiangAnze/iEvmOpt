import os
import subprocess
import json

from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg


class CfgBuilder:

    def __init__(self, _srcPath: str):
        self.srcPath = _srcPath  # 原bin文件的路径
        self.srcName = os.path.basename(_srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg/CfgOutput/"  # 输出的目录名
        self.__etherSolve()
        self.cfg = Cfg()
        self.__buildCfg()

    def __etherSolve(self):
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -H -o " + self.outputPath + self.srcName + "_cfg.html " + self.srcPath
        subprocess.Popen(cmd)
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -j -o " + self.outputPath + self.srcName + "_cfg.json " + self.srcPath
        subprocess.Popen(cmd)
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            cmd = "dot " + self.outputPath + self.srcName + "_cfg.gv -Tpng -o " + self.outputPath + self.srcName + ".png"
            subprocess.Popen(cmd)

    def __buildCfg(self):
        with open(self.outputPath + self.srcName + "_cfg.json ", 'r', encoding='UTF-8') as f:
            json_dict = json.load(f)
        for b in json_dict["runtimeCfg"]["nodes"]:  # 读取基本块
            # print(node)
            block = BasicBlock(b)
            self.cfg.addBasicBlock(block)
        for e in json_dict["runtimeCfg"]["successors"]:  # 读取边
            self.cfg.addEdge(e)

    def getCfg(self):
        return self.cfg
