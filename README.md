# pysct
Python wrapper for Xilinx's XSCT/XSDB console

This package based on the following requiremets:
 - [Running-SDK-project-in-other-software][1]
 - [Error during control Xilinx XSCT with pexpect][2]
 
 
## Example

```python
    win_xsct_executable = r'C:\Xilinx\SDK\2017.4\bin\xsct.bat'
    xsct_server = XsctServer(win_xsct_executable, port=PORT, verbose=False)
    xsct = Xsct('localhost', PORT)
    
    print("xsct's pid: {}".format(xsct.do('pid')))
    print(xsct.do('set a 5'))
    print(xsct.do('set b 4'))
    print("5+4={}".format(xsct.do('expr $a + $b')))

    xsct.close()
    xsct_server.stop_server()
```

Prints out:
```
xsct's pid: 13808
5
4
5+4=9

```
 
 
[1]: https://forums.xilinx.com/t5/Embedded-Development-Tools/Running-SDK-project-in-other-software/td-p/885535
[2]: https://stackoverflow.com/q/58733494/2506522