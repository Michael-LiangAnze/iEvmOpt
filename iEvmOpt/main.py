import sys
import Cfg

if __name__ == '__main__':
    if len(sys.argv) < 2:
        exit(-1)

    cfg = Cfg.CfgBuilder(sys.argv[1])


