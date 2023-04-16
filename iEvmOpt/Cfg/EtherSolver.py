import os
import subprocess
import json
import sys

import graphviz

from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg
from Utils import DotGraphGenerator
from Utils.Logger import Logger


class EtherSolver:

    def __init__(self, srcPath: str, isParseBefore: bool = False):
        """ 使用EtherSolve工具分析字节码文件，得到对应的json、html、gv文件
            并通过json文件构造cfg
        :param isParseBefore:之前是否已经得到过了输出文件，若为False则不再对字节码使用EtherSolve分析，而是直接读取对应的输出文件
        """
        self.srcPath = srcPath  # 原bin文件的路径
        self.srcName = os.path.basename(srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg\CfgOutput\\"  # 输出的目录名
        self.constructorCfg = Cfg()
        self.cfg = Cfg()
        self.constructorDataSeg = None  # 构建函数体后的数据段
        self.dataSeg = None  # 函数体后的数据段
        self.log = Logger()
        if not isParseBefore:
            self.__etherSolve()
        self.__buildCfg()
        # if not isParseBefore:
        #     dg = DotGraphGenerator(self.cfg.blocks.keys(), self.cfg.edges)
        #     dg.genDotGraph(self.outputPath, self.srcName)

    def __etherSolve(self):
        jarPath = os.path.dirname(__file__)+"\EtherSolve.jar"
        self.log.info("正在使用EtherSolve处理字节码")

        cmd = "java -jar " + jarPath + " -c -H -o " + self.outputPath + self.srcName + "_cfg.html " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass
        if p.returncode != 0:
            exit(-1)

        cmd = "java -jar " + jarPath + " -r -H -o " + self.outputPath + self.srcName + "_constructor_cfg.html " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        cmd = "java -jar " + jarPath + " -c -j -o " + self.outputPath + self.srcName + "_cfg.json " + self.srcPath
        p = subprocess.Popen(cmd)
        if p.wait() == 0:
            pass

        # 因为读取较大.gv文件进行rander时会出错，因此不在使用该方法生成图片，而是生成html进行分析
        # # 生成构建时cfg
        # cmd = "java -jar " + jarPath + " -r -d -o " + self.outputPath + self.srcName + "_constructor_cfg.gv " + self.srcPath
        # p = subprocess.Popen(cmd)
        # if p.wait() == 0:
        #     pass
        #
        # # 生成运行时cfg
        # cmd = "java -jar " + jarPath + " -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
        # p = subprocess.Popen(cmd)
        # if p.wait() == 0:
        #     pass
        #
        # # 读取构建函数的gv文件，生成png图片
        # with open(self.outputPath + self.srcName + "_constructor_cfg.gv ") as f:
        #     g = f.read()
        # dot = graphviz.Source(g)
        # dot.render(outfile=self.outputPath + self.srcName + "_constructor_cfg.png", format='png')
        #
        # # 读取运行时的gv文件，生成png图片
        # with open(self.outputPath + self.srcName + "_cfg.gv ") as f:
        #     g = f.read()
        # dot = graphviz.Source(g)
        # dot.render(outfile=self.outputPath + self.srcName + "_cfg.png", format='png')

        self.log.info("EtherSolve处理完毕")

    def __buildCfg(self):
        self.log.info("正在构建CFG")
        # 读入json文件
        with open(self.outputPath + self.srcName + "_cfg.json ", 'r', encoding='UTF-8') as f:
            jsonInfo = json.load(f)
        f.close()
        # 读取构建信息
        for b in jsonInfo["constructorCfg"]["nodes"]:  # 读取基本块
            block = BasicBlock(b)
            self.constructorCfg.addBasicBlock(block)
        for e in jsonInfo["constructorCfg"]["successors"]:  # 读取边
            self.constructorCfg.addEdge(e)
        self.constructorCfg.genBytecodeStr()

        # 读取运行时信息
        for b in jsonInfo["runtimeCfg"]["nodes"]:  # 读取基本块
            block = BasicBlock(b)
            self.cfg.addBasicBlock(block)
        for e in jsonInfo["runtimeCfg"]["successors"]:  # 读取边
            self.cfg.addEdge(e)
        self.cfg.genBytecodeStr()

        # 获取起始基本块和终止基本块
        self.cfg.initBlockId = min(self.cfg.blocks.keys())
        assert self.cfg.initBlockId == 0
        self.cfg.exitBlockId = max(self.cfg.blocks.keys())
        assert len(self.cfg.edges[self.cfg.exitBlockId]) == 0

        self.constructorCfg.initBlockId = min(self.constructorCfg.blocks.keys())
        assert self.constructorCfg.initBlockId == 0
        self.constructorCfg.exitBlockId = max(self.constructorCfg.blocks.keys())
        assert len(self.constructorCfg.edges[self.constructorCfg.exitBlockId]) == 0

        # 添加unconditional、conditional跳转目标块的信息
        for offset, b in self.cfg.blocks.items():
            if b.jumpType == "unconditional":
                b.jumpDest = list(self.cfg.edges[offset])
                # b.printBlockInfo()
            elif b.jumpType == "conditional":
                fallBlockOffset = b.offset + b.length
                dests = list(self.cfg.edges[offset])
                jumpiTrueOffset = dests[0] if dests[0] != fallBlockOffset else dests[1]
                b.jumpiDest[True] = jumpiTrueOffset
                b.jumpiDest[False] = fallBlockOffset
                # b.printBlockInfo()

        for offset, b in self.constructorCfg.blocks.items():
            if b.jumpType == "unconditional":
                b.jumpDest = list(self.constructorCfg.edges[offset])
                # b.printBlockInfo()
            elif b.jumpType == "conditional":
                fallBlockOffset = b.offset + b.length
                dests = list(self.constructorCfg.edges[offset])
                jumpiTrueOffset = dests[0] if dests[0] != fallBlockOffset else dests[1]
                b.jumpiDest[True] = jumpiTrueOffset
                b.jumpiDest[False] = fallBlockOffset
                # b.printBlockInfo()

        # 设置起始偏移量
        with open(self.srcPath, "r") as f:
            originalStr = f.read()  # 将原字符串读入
        funcBodyBeginIndex = originalStr.find(self.cfg.bytecodeStr)
        assert funcBodyBeginIndex != -1
        assert originalStr.count(self.cfg.bytecodeStr) == 1
        self.cfg.setBeginIndex(funcBodyBeginIndex // 2)  # 因为是字符串的偏移量，因此要除以2
        self.constructorCfg.setBeginIndex(0)  # 构造函数的起始偏移量是0

        # 注意，这里的构造函数数据段是指，构造函数函数字节码之后，运行时函数字节码之前的字符串
        self.constructorDataSeg = originalStr[self.constructorCfg.getBytecodeLen() * 2:funcBodyBeginIndex]
        # 这里的运行时数据段，不仅仅指运行时函数后面的data，还包括metadata
        self.dataSeg = originalStr[funcBodyBeginIndex + self.cfg.bytecodeLength * 2:]

        self.log.info("CFG构建完毕")
        # self.cfg.output()
        # self.constructorCfg.output()

    def getConstructorCfg(self):
        return self.constructorCfg

    def getCfg(self):
        return self.cfg

    def getConstructorDataSegStr(self):
        return self.constructorDataSeg

    def getDataSeg(self):
        return self.dataSeg
