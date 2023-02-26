import os
import subprocess


class CfgBuilder:

    def __init__(self, _srcPath: str):
        self.srcPath = _srcPath  # 原bin文件的路径
        self.srcName = os.path.basename(_srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg/CfgOutput/"  # 输出的目录名
        self.etherSolve()

    def etherSolve(self):
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -H -o " + self.outputPath + self.srcName + "_cfg.html " + self.srcPath
        subprocess.Popen(cmd)
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
        subprocess.Popen(cmd)
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -j -o " + self.outputPath + self.srcName + "_cfg.json " + self.srcPath
        subprocess.Popen(cmd)
        cmd = "dot " + self.outputPath + self.srcName + "_cfg.gv -Tpng -o " + self.outputPath + self.srcName + ".png"
        subprocess.Popen(cmd)

