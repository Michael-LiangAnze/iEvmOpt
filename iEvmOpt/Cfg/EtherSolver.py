import os
import subprocess
import json

import graphviz

from AssertionOptimizer.TagStacks.TagStack import TagStack
from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg
from Cfg.CfgRepairKit import CfgRepairKit
from Utils import DotGraphGenerator
from Utils.Logger import Logger


class EtherSolver:

    def __init__(self, srcPath: str, isParseBefore: bool = False, genPng=False):
        """ 使用EtherSolve工具分析字节码文件，得到对应的json、html、gv文件
            并通过json文件构造cfg
        :param isParseBefore:之前是否已经得到过了输出文件，若为False则不再对字节码使用EtherSolve分析，而是直接读取对应的输出文件
        :param genPng:生成png图片
        """
        self.srcPath = srcPath  # 原bin文件的路径
        self.genPng = genPng
        self.srcName = os.path.basename(srcPath).split(".")[0]  # 原bin文件的文件名
        self.outputPath = "Cfg\CfgOutput\\"  # 输出的目录名
        self.constructorCfg = Cfg()
        self.cfg = Cfg()
        self.constructorDataSeg = None  # 构建函数体后的数据段
        self.dataSeg = None  # 函数体后的数据段
        self.log = Logger()
        self.timeOutLimit = 300  # 5min
        if not isParseBefore:
            self.__etherSolve()
        self.__buildCfg()
        # if not isParseBefore:
        #     dg = DotGraphGenerator(self.cfg.blocks.keys(), self.cfg.edges)
        #     dg.genDotGraph(self.outputPath, self.srcName)


    def __etherSolve(self):
        jarPath = os.path.dirname(__file__) + "\EtherSolve.jar"
        self.log.info("正在使用EtherSolve处理字节码")

        cmd = "java -jar " + jarPath + " -c -H -o " + self.outputPath + self.srcName + "_cfg.html " + self.srcPath
        p = subprocess.Popen(cmd)
        returnCode = 0
        try:
            p.wait(timeout=self.timeOutLimit)
            returnCode = p.returncode
        except:
            cmd = "taskkill /F /PID " + str(p.pid)
            os.system(cmd)  # 杀死子进程
            returnCode = -1
            self.log.fail("EtherSolve处理超时")
        if returnCode != 0:
            self.log.fail("EtherSolve处理出错")

        cmd = "java -jar " + jarPath + " -r -H -o " + self.outputPath + self.srcName + "_constructor_cfg.html " + self.srcPath
        p = subprocess.Popen(cmd)
        try:
            p.wait(timeout=self.timeOutLimit)
            returnCode = p.returncode
        except:
            cmd = "taskkill /F /PID " + str(p.pid)
            os.system(cmd)  # 杀死子进程
            returnCode = -1
            self.log.fail("EtherSolve处理超时")
        if returnCode != 0:
            self.log.fail("EtherSolve处理出错")

        cmd = "java -jar " + jarPath + " -c -j -o " + self.outputPath + self.srcName + "_cfg.json " + self.srcPath
        p = subprocess.Popen(cmd)
        try:
            p.wait(timeout=self.timeOutLimit)
            returnCode = p.returncode
        except:
            cmd = "taskkill /F /PID " + str(p.pid)
            os.system(cmd)  # 杀死子进程
            returnCode = -1
            self.log.fail("EtherSolve处理超时")
        if returnCode != 0:
            self.log.fail("EtherSolve处理出错")

        if self.genPng:
            # 生成构建时cfg
            cmd = "java -jar " + jarPath + " -r -d -o " + self.outputPath + self.srcName + "_constructor_cfg.gv " + self.srcPath
            p = subprocess.Popen(cmd)
            try:
                p.wait(timeout=self.timeOutLimit)
                returnCode = p.returncode
            except:
                cmd = "taskkill /F /PID " + str(p.pid)
                os.system(cmd)  # 杀死子进程
                returnCode = -1
                self.log.fail("EtherSolve处理超时")
            if returnCode != 0:
                self.log.fail("EtherSolve处理出错")

            # 生成运行时cfg
            cmd = "java -jar " + jarPath + " -c -d -o " + self.outputPath + self.srcName + "_cfg.gv " + self.srcPath
            p = subprocess.Popen(cmd)
            try:
                p.wait(timeout=self.timeOutLimit)
                returnCode = p.returncode
            except:
                cmd = "taskkill /F /PID " + str(p.pid)
                os.system(cmd)  # 杀死子进程
                returnCode = -1
                self.log.fail("EtherSolve处理超时")
            if returnCode != 0:
                self.log.fail("EtherSolve处理出错")

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

        #############               使用CfgRepairKit进行检测和修复              #############
        constructorKit = CfgRepairKit(self.constructorCfg)
        constructorKit.fix()
        if not constructorKit.isFixed():  # 修复失败
            self.log.fail("构造函数边修复失败")
        else:
            self.log.info("构造函数边修复成功")
        self.constructorCfg.edges, self.constructorCfg.inEdges = constructorKit.getRepairedEdges()

        runtimeKit = CfgRepairKit(self.cfg)
        runtimeKit.fix()
        if not runtimeKit.isFixed():  # 修复失败
            self.log.fail("运行时函数边修复失败")
        else:
            self.log.info("运行时函数边修复成功")
        self.cfg.edges, self.cfg.inEdges = runtimeKit.getRepairedEdges()

        ##############              修复结束                   ################

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

        # 对每一个unconditional jump的block，进行tagStack执行，看是否有可能出现：
        #   jump的地址是在block内部计算得到的
        # 这种情况下，这个block也有可能是调用节点
        # 因为不知道栈中原有的内容，因此在做执行之前，先往栈中压入16个None
        preInfo = [[None, None, None, None, False] for i in range(64)]  # 64个总够用了吧
        pushInfo = None
        tagStack = TagStack(self.cfg)
        for offset, b in self.cfg.blocks.items():
            if b.jumpType != "unconditional":
                continue
            tagStack.clear()
            tagStack.setTagStack(preInfo)
            tagStack.setBeginBlock(offset)
            while not tagStack.allInstrsExecuted():
                if tagStack.isLastInstr():
                    pushInfo = tagStack.getTagStackTop()
                tagStack.execNextOpCode()
            if pushInfo[0] is None:  # 置为了untag
                continue
            # 检查pushinfo是否与可能的跳转边一致
            # 如果一致，则这个跳转边可能是调用边
            # 如果一致，则这个跳转边一定不是返回边
            if pushInfo[0] in self.cfg.jumpDests:  # and self.cfg.inEdges[pushInfo[0]].__len__() > 1错误的
                b.couldBeCaller = True

        tagStack = TagStack(self.constructorCfg)
        for offset, b in self.constructorCfg.blocks.items():
            if b.jumpType != "unconditional":
                continue
            tagStack.clear()
            tagStack.setTagStack(preInfo)
            tagStack.setBeginBlock(offset)
            while not tagStack.allInstrsExecuted():
                if tagStack.isLastInstr():
                    pushInfo = tagStack.getTagStackTop()
                tagStack.execNextOpCode()
            if pushInfo[0] is None:  # 置为了untag
                continue
            # 检查pushinfo是否与可能的跳转边一致
            # 如果一致，则这个跳转边可能是调用边
            # 如果一致，则这个跳转边一定不是返回边
            if pushInfo[0] in self.constructorCfg.jumpDests:  # and self.cfg.inEdges[pushInfo[0]].__len__() > 1错误的
                b.couldBeCaller = True

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
