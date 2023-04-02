import os
import subprocess
import json

import graphviz

from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg
from Utils import DotGraphGenerator
from Utils.Logger import Logger


class CfgBuilder:

    def __init__(self, srcPath: str, isParseBefore: bool = False):
        """ 使用EtherSolve工具分析字节码文件，得到对应的json、html、gv文件
            并通过json文件构造cfg
        :param isParseBefore:之前是否已经得到过了输出文件，若为False则不再对字节码使用EtherSolve分析，而是直接读取对应的输出文件
        """
        self.srcPath = srcPath  # 原bin文件的路径
        self.srcName = os.path.basename(srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg/CfgOutput/"  # 输出的目录名
        self.constructorCfg = Cfg()
        self.cfg = Cfg()
        self.log = Logger()
        if not isParseBefore:
            self.__etherSolve()
        self.__buildCfg()
        if not isParseBefore:
            dg = DotGraphGenerator(self.cfg.blocks.keys(), self.cfg.edges)
            dg.genDotGraph(self.outputPath, self.srcName)

    def __etherSolve(self):
        self.log.info("正在使用EtherSolve处理字节码")
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -H -o " + self.outputPath + self.srcName + "_cfg.html " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -j -o " + self.outputPath + self.srcName + "_cfg.json " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        # 生成构建时cfg
        cmd = "java -jar ./Cfg/EtherSolve.jar -r -d -o " + self.outputPath + self.srcName + "_constructor_cfg.gv " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        # 生成运行时cfg
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        # 读取构建函数的gv文件，生成png图片
        with open(self.outputPath + self.srcName + "_constructor_cfg.gv ") as f:
            g = f.read()
        dot = graphviz.Source(g)
        dot.render(outfile=self.outputPath + self.srcName + "_constructor_cfg.png", format='png')

        # 读取运行时的gv文件，生成png图片
        with open(self.outputPath + self.srcName + "_cfg.gv ") as f:
            g = f.read()
        dot = graphviz.Source(g)
        dot.render(outfile=self.outputPath + self.srcName + "_cfg.png", format='png')


        self.log.info("EtherSolve处理完毕")

    def __buildCfg(self):
        self.log.info("正在构建CFG")
        # 读入原文件
        with open(self.outputPath + self.srcName + "_cfg.json ", 'r', encoding='UTF-8') as f:
            json_dict = json.load(f)
        f.close()
        # 读取构建信息
        for b in json_dict["constructorCfg"]["nodes"]:  # 读取基本块
            block = BasicBlock(b)
            self.constructorCfg.addBasicBlock(block)
        for e in json_dict["constructorCfg"]["successors"]:  # 读取边
            self.constructorCfg.addEdge(e)

        # 读取运行时信息
        for b in json_dict["runtimeCfg"]["nodes"]:  # 读取基本块
            block = BasicBlock(b)
            self.cfg.addBasicBlock(block)
        for e in json_dict["runtimeCfg"]["successors"]:  # 读取边
            self.cfg.addEdge(e)

        # 获取起始基本块和终止基本块
        self.cfg.initBlockId = min(self.cfg.blocks.keys())
        assert self.cfg.initBlockId == 0
        self.cfg.exitBlockId = max(self.cfg.blocks.keys())
        assert len(self.cfg.edges[self.cfg.exitBlockId]) == 0

        # 添加unconditional、conditional跳转目标块的信息
        for offset, b in self.cfg.blocks.items():
            if b.jumpType == "unconditional":
                b.jumpDest = list(self.cfg.edges[offset])
                # b.printBlockInfo()
            elif b.jumpType == "conditional":
                fallBlockOff = b.offset + b.length
                dests = list(self.cfg.edges[offset])
                jumpiTrueOff = dests[0] if dests[0] != fallBlockOff else dests[1]
                b.jumpiDest[True] = jumpiTrueOff
                b.jumpiDest[False] = fallBlockOff
                # b.printBlockInfo()

        self.log.info("CFG构建完毕")
        # self.cfg.output()
        # self.constructorCfg.output()

    def getConstructorCfg(self):
        return self.constructorCfg

    def getCfg(self):
        return self.cfg
