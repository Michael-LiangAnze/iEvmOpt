class HelpInfo:
    '''
    一条帮助信息
    '''

    def __init__(self, abbreviation: str, fullName: str, usage: str, alternative: bool = True):
        '''
        记录帮助信息的结构体
        :param abbreviation: 缩写，如-v
        :param fullName: 全称，如--version
        :param usage: 作用
        :param alternative: 是否是可选参数
        '''
        self.abbreviation = abbreviation
        self.fullName = fullName
        self.usage = usage
        self.alternative = alternative


class Helper:
    '''
    存储帮助信息
    '''

    def __init__(self):
        self.introduce = "iEvmOpt, optimize a smart contract from Ethereum bytecode"
        self.requiredArgslist = ["<source>", "<outputPath>", "<outputName>"]
        self.version = "1.0"

        self.HelpInfos = []
        self.HelpInfos.append(HelpInfo("", "<source>", "Bytecode string or file containing it", False))
        self.HelpInfos.append(HelpInfo("", "<outputPath>", "Output path of results.", False))
        self.HelpInfos.append(HelpInfo("", "<outputName>", "Output name of optimized bytecode.", False))

        self.HelpInfos.append(HelpInfo("-h", "--help", "Show this help message and exit."))
        self.HelpInfos.append(
            HelpInfo("-pd", "--process-detail", "Print detailed information during optimization process."))
        self.HelpInfos.append(HelpInfo("-H", "--html",
                                       "Export constructor'CFG and runtime'CFG as graphic HTML reports. Graphviz is required!"))
        self.HelpInfos.append(HelpInfo("-v", "--version", "Print version information and exit."))

    def getHelpInfo(self):
        res = ""
        res += self.introduce + "\n"
        res += "Usage: iEvmOpt " + " ".join(self.requiredArgslist) + " ({})".format(
            " | ".join([i.abbreviation for i in self.HelpInfos if i.alternative])) + "\n"
        res += "Notice: If used to optimize an bytecode, these three parameters must appear in this order at the beginning of all parameters: {}".format(
            " ".join(self.requiredArgslist)) + "\n"
        res += "Options and arguments:\n"
        for hi in self.HelpInfos:
            res += hi.abbreviation.ljust(5," ") + hi.fullName.ljust(20," ")
            lines = []
            limit = 80
            i = 0
            while i < len(hi.usage):
                lines.append(hi.usage[i:i+limit])
                i += limit
            for i in range(len(lines)):
                if i == 0:
                    res += lines[i] + "\n"
                else:
                    res += "".join([" " for i in range(25)]) + lines[i] + "\n"

        return res

    def getVersion(self):
        return self.version
