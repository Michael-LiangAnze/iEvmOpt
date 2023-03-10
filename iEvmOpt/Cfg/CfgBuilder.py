import os
import subprocess
import json

import graphviz

from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg
from Utils import DotGraphGenerator
from Utils.Logger import Logger


class CfgBuilder:

    def __init__(self, _srcPath: str, isParseBefore: bool = False):
        """ 使用EtherSolve工具分析字节码文件，得到对应的json、html、gv文件
            并通过json文件构造cfg
        :param isParseBefore:之前是否已经得到过了输出文件，若为False则不再对字节码使用EtherSolve分析，而是直接读取对应的输出文件
        """
        self.srcPath = _srcPath  # 原bin文件的路径
        self.srcName = os.path.basename(_srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg/CfgOutput/"  # 输出的目录名
        self.cfg = Cfg()
        self.log = Logger()
        if not isParseBefore:
            self.__etherSolve()
        self.__buildCfg()
        if not isParseBefore:
            dg = DotGraphGenerator(self.cfg.edges, self.cfg.blocks.keys())
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
        cmd = "java -jar ./Cfg/EtherSolve.jar -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        with open(self.outputPath + self.srcName + "_cfg.gv ") as f:
            g = f.read()  # 读取已经生成的gv文件
        dot = graphviz.Source(g)
        dot.render(outfile=self.outputPath + self.srcName + "_cfg.png", format='png')
        self.log.info("EtherSolve处理完毕")

    def __buildCfg(self):
        self.log.info("正在构建CFG")
        with open(self.outputPath + self.srcName + "_cfg.json ", 'r', encoding='UTF-8') as f:
            json_dict = json.load(f)
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

        # 添加函数头信息
        # for offset, node in self.cfg.blocks.items():
        #     if node.cfgType == "dispatcher":  # dispatcher->common
        #         for out in self.cfg.edges[offset]:
        #             if self.cfg.blocks[out].cfgType == "common":
        #                 self.cfg.blocks[out].isFuncBegin = True
        #     elif node.cfgType == "common" and node.blockType == "unconditional":  # common-(unconditional)->common
        #         for out in self.cfg.edges[offset]:
        #             if self.cfg.blocks[out].cfgType == "common":
        #                 self.cfg.blocks[out].isFuncBegin = True
        self.log.info("CFG构建完毕")

    def getCfg(self):
        return self.cfg
