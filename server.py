import threading, shutil, psutil, random, time, ssl, re, os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from getSens import getSens

DIRNAME = f"{getSens('dir')[0]}"
HOST_NAME = ''
PORT_NUMBER = 80
MAXDIRSIZE = 100

fileTypes = ["mp4", "png", "webm", "mov", "jpg", "jpeg", "gif", "txt"]

parentDir = os.getcwd()
if not os.path.isdir(DIRNAME):
	os.mkdir(DIRNAME)
os.chdir(DIRNAME)

class strArr:
    def __init__(self, startArr):
        self.arr = startArr
    def __iadd__(self, s):
        if type(s) == str:
            self.arr.append(s)
        elif type(s) == list:
            self.arr.extend(s)
        return self

def fileBytes(filename):
    return open(filename, 'rb').read()

def getInfo(s):
    path = s.path[1:].split('?', 1)
    args = []
    if len(path) > 1:
        args = path[1].split("&")
    return (path[0], args, os.path.splitext(path[0])[1][1:])

def exists(s):
    return os.path.isfile(s) or os.path.isdir(s)

def sizeof_fmt(num, suffix='B'): #https://stackoverflow.com/a/1094933
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)

def getSystemStats():
    total, used, free = shutil.disk_usage(DIRNAME)
    memory = psutil.virtual_memory()
    return (sizeof_fmt(used), sizeof_fmt(total), psutil.cpu_percent(), sizeof_fmt(memory.used), sizeof_fmt(memory.total))

diskused, disksize, cpu, ramUsed, totalRam = getSystemStats()

def updateMemory():
    global cpu, ramUsed, totalRam
    while 1:
        try:
            diskused, disksize, cpu, ramUsed, totalRam = getSystemStats()
            time.sleep(1)
        except Exception as e:
            print(e)
            time.sleep(1)

systemStatUpdateThread = threading.Thread(target = updateMemory)
systemStatUpdateThread.start()

class MyHandler(SimpleHTTPRequestHandler):
    def copyfile(self, infile, outfile):
        if not 'Range' in self.headers:
            SimpleHTTPRequestHandler.copyfile(self, infile, outfile)
            return
        outfile = open(outfile, 'wb')
        start, end = self.range
        infile.seek(start)
        bufsize = 64*1024 ## 64KB
        while True:
            buf = infile.read(bufsize)
            if not buf:
                break
            outfile.write(buf)

    def do_HEAD(self):
        t = self.path[1:]
        if os.path.isdir(t):
            self.send_response(200)
        elif os.path.isfile(t):
            self.send_response(201)
        else:
            self.send_response(202)
        self.end_headers()
        print("H - " + t)

    def do_GET(self):
        ignoreOutput = False

        path, args, ext = getInfo(self)
        pathname = re.sub(r"^([\/,\. ]{1,})", '', path.lower()).replace('../', '')
        abspath = f"{os.getcwd()}/{pathname}".strip()
        if not abspath.lower().startswith(DIRNAME.lower()):
            abspath = f"{DIRNAME}/@error"

        CT = "text/html"
        code = 201
        mode = ""

        if len(pathname.strip().replace('/', '')) < 1:
            mode = "index"
        elif pathname == "icons/":
            mode = "icon"
            CT = "image/x-icon"
            code = 200
        elif pathname == "@stats":
            mode = "stats"
            code = 200
            ignoreOutput = True
        elif "range" in self.headers and exists(abspath):
            mode = "vidpart"
            CT = None
        elif os.path.isfile(abspath) or "thumb" in args:
            code = 200
            if ext == "mp4":
                if "video" in args:
                    mode = "vidpage"
                else:
                    mode = "FILE"
                    CT = "video/mp4"
            elif ext in ["png", "jpg", "gif", "jpeg"]:
                mode = "FILE"
                CT = f"image/{ext}"
            else:
                mode = "FILE"
                CT = f"text"
        elif os.path.isdir(abspath):
            if 'index.html' in os.listdir(abspath):
                mode = "dirIndex"
            else:
                mode = "dirmode"
        if not ignoreOutput:
            print(f"G ({mode}) - " + (pathname if len(pathname) > 0 else "INDEX"))

        if CT:
            self.send_response(code)
            self.send_header("Content-type", CT)
            self.end_headers()

        if mode == "stats":
            self.wfile.write(f'''{{"diskused":"{diskused}","disksize":"{disksize}","cpu":{cpu},"ramUsed":"{ramUsed}","totalRam":"{totalRam}"}}'''.encode('utf-8'))
        elif mode == "icon":
            self.wfile.write(fileBytes(f"{parentDir}/icons/favicon.ico"))
        elif mode == "index":
            self.wfile.write(fileBytes(f"{parentDir}/index.html"))
        elif mode == "dirIndex":
            self.wfile.write(fileBytes(f"{abspath}/index.html"))
        elif mode == "FILE":
            if os.path.isfile(abspath):
                self.wfile.write(fileBytes(abspath))
            else:
                self.wfile.write(fileBytes(f"{DIRNAME}/@files/question.png"))
        elif mode == "vidpart":
            path = abspath
            ctype = self.guess_type(path)
            f = open(path, 'rb')
            fs = os.fstat(f.fileno())
            size = fs[6]
            start, end = 0, size-1
            start, end = self.headers.get('Range').strip().strip('bytes=').split('-')
            if start == "":
                try:
                    end = int(end)
                except ValueError as e:
                    self.send_error(400, 'invalid range')
                start = size - end
            else:
                try:
                    start = int(start)
                except ValueError as e:
                    self.send_error(400, 'invalid range')
                    start = 0

                if int(start) >= int(size):
                    self.send_error(416, self.responses.get(416)[0])
                if end == "":
                    end = size-1
                else:
                    try:
                        end = int(end)
                    except ValueError as e:
                        self.send_error(400, 'invalid range')

            start = max(start, 0)
            end = min(end, size-1)
            self.range = (start, end)
            l = end-start+1
            if 'Range' in self.headers:
                self.send_response(206)
            else:
                self.send_response(200)
            self.send_header('Content-type', ctype)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Range',
                             'bytes %s-%s/%s' % (start, end, size))
            self.send_header('Content-Length', str(l))
            self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
            self.end_headers()
            self.copyfile(open(path, 'rb'), path + '_')
            try:
                self.wfile.write(fileBytes(path+'_'))
            except Exception as e:
                pass
            if os.path.isfile(f := path+"_"):
                os.remove(f)

        elif mode == "vidpage":
            self.wfile.write(f'''<html>
    <head>
    	<title> Download Video </title>
    	<link href="https://fonts.googleapis.com/icon?family=Material+Icons"
    		  rel="stylesheet">
		<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
        
        <style>
            body {{
                text-align: center;
            }}
            .DB {{
                width: 18vh;
                height: 6vh;
                background-color: rgb(54, 135, 125);
                border: 0;
                border-radius: 1vh;
                text-transform: uppercase;
                margin: 0 auto;
                transition: background-color 0.2s;
                cursor: pointer;
                font-family: Roboto, Segoe UI, sans-serif;
                box-shadow: rgba(0, 0, 0, 0.14) 0px 2px 2px 0px, rgba(0, 0, 0, 0.12) 0px 3px 1px -2px, rgba(0, 0, 0, 0.2) 0px 1px 5px 0px;
            }}
            .DB:hover {{
            	background-color: rgb(61, 153, 140);
            }}
            .txt {{
                color: white;
                font-size: 2vh;
                text-align: center;
                vertical-align: middle;
                text-decoration: none;
                font-weight: 500;
            }}
            i {{
			    vertical-align: middle;
				line-height: 0;
				margin-top: -0.7vh;
				font-size: 3vh;
			}}
            .vid {{
                padding-top: 5px;
            }}
            video:focus {{
            	outline: 0;
            }}
        </style>
        <script>
            document.addEventListener("keydown", function(e) {{
              if ((window.navigator.platform.match("Mac") ? e.metaKey : e.ctrlKey)  && e.keyCode == 83) {{
                e.preventDefault();
                document.getElementById('download').click();
              }}
            }}, false);
        </script>
    </head>
    <body style="background-color:#000000;">
        <button class="DB">
            <a class="txt" href="{path.split('/')[-1]}" id="download" download="video{random.randint(10000,100000)}.mp4">
            	<i class="material-icons left">save_alt</i>
            	Download
            </a>
        </button>
        <video controls autoplay width="100%" height="90%" class="vid">
            <source src="{path.split('/')[-1]}" type="video/mp4">
        </video>
    </body>
</html>'''.encode('utf-8'))
        elif mode == "dirmode":
            dirFiles = [i for i in os.listdir(abspath) if i != "thumb" and os.path.splitext(i)[1][1:] not in ["db"]]
            dirFiles.sort(key = lambda x: os.stat(f"{abspath}/{x}").st_mtime)
            dirFiles = dirFiles[::-1]
            seg = 0
            for i in args:
                if i.startswith("page="):
                    try:
                        seg = int(i.split('=', 1)[1]) - 1
                    except Exception as e:
                        pass
                    break
            pageCount = int(len(dirFiles) / MAXDIRSIZE) + 1
            if seg is not min(max(0, seg), pageCount):
                newFiles = []
            else:
                newFiles = [i.replace('\\', '/').replace('//', '/') for i in dirFiles[seg * MAXDIRSIZE : (seg + 1) * MAXDIRSIZE]]

            TB, NL = '\t', '\n'
            prefix = f'''<meta charset="UTF-8">
<html>
    <script>
        var test = [{", ".join([f'"{i}"' for i in newFiles])}];
        var name = "{path}";
        var page = {seg + 1};
        var pageCount = {pageCount};
    </script>'''
            self.wfile.write(prefix.encode('utf-8'))
            self.wfile.write(fileBytes(f"{parentDir}/listing.html"))
            return
        else:
            self.wfile.write('<script>var url = window.location.href; var arr = url.split("/"); window.location.replace(arr[0]+"//"+window.location.hostname);</script>'.encode('utf-8'))

    def log_message(self, format, *args):
        #self.client_address[0] is the user IP
        #print(' '.join(args))
        pass

if __name__ == '__main__':
    server_class = ThreadingHTTPServer
    httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
    #httpd.socket = ssl.wrap_socket(httpd.socket, certfile = f"{parentDir}/server.pem", keyfile = f"{parentDir}/other.pem", server_side=True)
    print("Started.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()