import os
import shutil
import signal
import subprocess
import json
from AssertionOptimizer.TagStacks.TagStack import TagStack
from Cfg.BasicBlock import BasicBlock
from Cfg.Cfg import Cfg
from Cfg.CfgRepairKit import CfgRepairKit
from Utils.Logger import Logger
import platform

class EtherSolver:

    def __init__(self, srcPath: str, outputPath: str, outputHtml=False):
        """ 使用EtherSolve工具分析字节码文件，得到对应的json、html文件并通过json文件构造cfg
        :param srcPath:输入字节码路径
        :param outputPath:输出路径
        :param outputHtml:生成CFG的HTML文件
        """
        self.srcPath = srcPath  # 输入bin文件的路径
        self.outputPath = outputPath  # 输出的目录名
        self.outputHtml = outputHtml
        self.srcName = os.path.basename(srcPath).split(".")[0]  # 原bin文件的文件名

        self.constructorCfg = Cfg()
        self.cfg = Cfg()
        self.constructorDataSeg = None  # 构建函数体后的数据段
        self.dataSeg = None  # 函数体后的数据段
        self.log = Logger()
        self.timeOutLimit = 300  # 5min

        # 确定当前平台，以方便杀死子进程
        self.plf = platform.system().lower() # 'windows'/ 'linux'

    def execSolver(self):
        self.log.info("正在使用EtherSolve生成JSON文件")

        # 对文件的路径进行处理
        #  坑：EtherSolve不接受绝对地址的输出目录，因此将输入目录和输出目录改为相对目录
        # 相对与当前文件的相对地址，然后在使用子进程进行处理时，指定工作目录为当前文件所在目录
        # 即，对于EtherSolve的一切输出，将暂时输出到CfgOutput当中，后面我们再将它们移动到输出目录里
        relSrcPathForEs = os.path.relpath(self.srcPath, os.path.dirname(__file__))  # 为EtherSolve确定的相对路径

        # 生成JSON文件
        returnCode = 0
        cmd = "java -jar EtherSolve.jar -c -j -o CfgOutput/" + self.srcName + "_cfg.json " + relSrcPathForEs
        p = subprocess.Popen(cmd, cwd=os.path.dirname(__file__),shell=True)
        try:
            p.wait(timeout=self.timeOutLimit)
            returnCode = p.returncode
        except: # 超时
            if self.plf == 'windows':
                cmd = "taskkill /F /PID " + str(p.pid)
                os.system(cmd)
            elif self.plf == 'linux':
                os.killpg(p.pid, signal.SIGKILL)
            returnCode = -1
            self.log.fail("EtherSolve处理超时")
            exit(-1)
        if returnCode != 0:
            self.log.fail("EtherSolve处理出错")
            exit(-1)

        # 生成HTML用于观察测试
        if self.outputHtml:
            self.log.info("正在使用EtherSolve生成运行时CFG的HTML报告")

            cmd = "java -jar EtherSolve.jar -c -H -o CfgOutput/" + self.srcName + "_runtime_cfg.html " + relSrcPathForEs
            p = subprocess.Popen(cmd, cwd=os.path.dirname(__file__),shell=True)
            try:
                p.wait(timeout=self.timeOutLimit)
                returnCode = p.returncode
            except:
                if self.plf == 'windows':
                    cmd = "taskkill /F /PID " + str(p.pid)
                    os.system(cmd)
                elif self.plf == 'linux':
                    os.killpg(p.pid, signal.SIGKILL)
                returnCode = -1
                self.log.fail("EtherSolve处理超时")
                exit(-1)
            if returnCode != 0:
                self.log.fail("EtherSolve处理出错")
                exit(-1)

            self.log.info("正在使用EtherSolve生成构造函数CFG的HTML报告")
            cmd = "java -jar EtherSolve.jar -r -H -o CfgOutput/" + self.srcName + "_constructor_cfg.html " + relSrcPathForEs
            p = subprocess.Popen(cmd, cwd=os.path.dirname(__file__),shell=True)
            try:
                p.wait(timeout=self.timeOutLimit)
                returnCode = p.returncode
            except:
                if self.plf == 'windows':
                    cmd = "taskkill /F /PID " + str(p.pid)
                    os.system(cmd)
                elif self.plf == 'linux':
                    os.killpg(p.pid, signal.SIGKILL)
                returnCode = -1
                self.log.fail("EtherSolve处理超时")
                exit(-1)
            if returnCode != 0:
                self.log.fail("EtherSolve处理出错")
                exit(-1)

        # 使用输出文件构建CFG
        self.__buildCfg()

        # 为了不占用iEvmOpt的大小，将所有的输出文件都移动到输出目录当中
        # 如果原目录下已经存在同名的文件，则直接删除
        if os.path.exists(self.outputPath + "/" + self.srcName + "_cfg.json"):
            os.remove(self.outputPath + "/" + self.srcName + "_cfg.json")
        shutil.move(os.path.dirname(__file__) + "/CfgOutput/" + self.srcName + "_cfg.json", self.outputPath)
        if self.outputHtml:
            if os.path.exists(self.outputPath + "/" + self.srcName + "_runtime_cfg.html"):
                os.remove(self.outputPath + "/" + self.srcName + "_runtime_cfg.html")
            shutil.move(os.path.dirname(__file__) + "/CfgOutput/" + self.srcName + "_runtime_cfg.html", self.outputPath)
            if os.path.exists(self.outputPath + "/" + self.srcName + "_constructor_cfg.html"):
                os.remove(self.outputPath + "/" + self.srcName + "_constructor_cfg.html")
            shutil.move(os.path.dirname(__file__) + "/CfgOutput/" + self.srcName + "_constructor_cfg.html",
                        self.outputPath)

        self.log.info("EtherSolve处理完毕")

    def __buildCfg(self):
        self.log.info("正在构建CFG")
        # 读入json文件
        with open(os.path.dirname(__file__) + "/CfgOutput/" + self.srcName + "_cfg.json", 'r', encoding='UTF-8') as f:
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

        # 避个坑，这里检查一下是否存在invalid，如果都不存在invalid，则在这里就可以返回了，在Assertion里面检测到没有invalid,程序会结束
        if not self.cfg.invalidExist:
            self.constructorDataSeg = ""  # 设置一下，不然会报错
            self.dataSeg = ""
            return

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
        # 修复不一定是成功的，毕竟只是做简单的dfs
        # 只是输出Warning，后续还要对没有入边的节点做判断，看看是否属于是selfdestruct引起的，如果是，则尝试再次进行修复

        runtimeKit = CfgRepairKit(self.cfg)
        runtimeKit.fix()
        if not runtimeKit.isFixed():  # 修复失败
            self.log.warning("运行时函数边修复失败")
        else:
            self.log.info("运行时函数边修复成功")
        self.cfg.edges, self.cfg.inEdges = runtimeKit.getRepairedEdges()

        # ##############              修复结束                   ################

        # 添加unconditional、conditional跳转目标块的信息
        for offset, b in self.cfg.blocks.items():
            if b.jumpType == "unconditional":
                b.jumpDest = list(self.cfg.edges[offset])
            elif b.jumpType == "conditional":
                fallBlockOffset = b.offset + b.length
                dests = list(self.cfg.edges[offset])
                jumpiTrueOffset = dests[0] if dests[0] != fallBlockOffset else dests[1]
                b.jumpiDest[True] = jumpiTrueOffset
                b.jumpiDest[False] = fallBlockOffset

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
        # 因为不知道栈中原有的内容，因此在做执行之前，先往栈中压入128个None
        # 为了获取cfg中Push过的所有数据，在这里记录一下
        pushedData = set()
        preInfo = [[None, None, None, None, False] for i in range(128)]
        pushInfo = None
        tagStack = TagStack(self.cfg)
        for offset, b in self.cfg.blocks.items():
            if b.jumpType != "unconditional":
                continue
            tagStack.clear()
            tagStack.setTagStack(preInfo)
            tagStack.setBeginBlock(offset)
            while not tagStack.allInstrsExecuted():
                opcode = tagStack.getOpcode()
                if tagStack.isLastInstr():
                    pushInfo = tagStack.getTagStackTop()
                tagStack.execNextOpCode()
                if 0x60 <= opcode <= 0x7f:  # 是一个push指令，获取push的数据
                    tmp = tagStack.getTagStackTop()
                    pushedData.add(tmp[0])
            if pushInfo[0] is None:  # 置为了untag
                continue
            # 检查pushinfo是否与可能的跳转边一致
            # 如果一致，则这个跳转边可能是调用边
            # 如果一致，则这个跳转边一定不是返回边
            if pushInfo[0] in self.cfg.jumpDests:  # and self.cfg.inEdges[pushInfo[0]].__len__() > 1错误的
                b.couldBeCaller = True
        self.cfg.pushedData = pushedData

        pushedData = set()
        tagStack = TagStack(self.constructorCfg)
        for offset, b in self.constructorCfg.blocks.items():
            if b.jumpType != "unconditional":
                continue
            tagStack.clear()
            tagStack.setTagStack(preInfo)
            tagStack.setBeginBlock(offset)
            while not tagStack.allInstrsExecuted():
                opcode = tagStack.getOpcode()
                if tagStack.isLastInstr():
                    pushInfo = tagStack.getTagStackTop()
                tagStack.execNextOpCode()
                if 0x60 <= opcode <= 0x7f:  # 是一个push指令，获取push的数据
                    tmp = tagStack.getTagStackTop()
                    pushedData.add(tmp[0])
            if pushInfo[0] is None:  # 置为了untag
                continue
            # 检查pushinfo是否与可能的跳转边一致
            # 如果一致，则这个跳转边可能是调用边
            # 如果一致，则这个跳转边一定不是返回边
            if pushInfo[0] in self.constructorCfg.jumpDests:  # and self.cfg.inEdges[pushInfo[0]].__len__() > 1错误的
                b.couldBeCaller = True
        self.constructorCfg.pushedData = pushedData

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
