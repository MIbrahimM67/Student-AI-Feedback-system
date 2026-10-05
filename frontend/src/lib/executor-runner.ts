// Trusted harness runs inside the disposable microVM, never on the web server.
export const EXECUTOR_RUNNER = String.raw`
import json, os, pwd, resource, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
student = pwd.getpwnam('student')
source_names = {'python': 'solution.py', 'cpp': 'solution.cpp', 'java': 'Main.java'}
language = request['language']
root = Path(tempfile.mkdtemp(prefix='grade-', dir='/tmp'))
root.chmod(0o755)
source = root / source_names[language]
source.write_text(request['code'])
source.chmod(0o444)

def limit_child(memory, seconds, work):
    os.setsid()
    os.setgroups([])
    os.setgid(student.pw_gid)
    os.setuid(student.pw_uid)
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    file_limit = 8 * 1024 * 1024 if seconds == 15 else 65536
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if memory:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    os.chdir(work)

def run(command, stdin, work, compile_step=False):
    start = time.monotonic()
    seconds = 15 if compile_step else 5
    memory = 512 * 1024 * 1024 if compile_step else 256 * 1024 * 1024
    # JVM reserves virtual memory independently of its bounded heap. The VM
    # itself is isolated and limited to 2 GB; Java heap is capped below.
    if language == 'java': memory = 0
    timed_out = False
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(work), 'LANG': 'C.UTF-8'},
            preexec_fn=lambda: limit_child(memory, seconds, work))
        try:
            process.communicate(stdin.encode(), timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        finally:
            # Kill detached children in the process group even if main exited.
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        timed_out = timed_out or process.returncode in (-signal.SIGXCPU, -signal.SIGKILL)
        out.seek(0); err.seek(0)
        stdout = out.read(16001); stderr = err.read(16001)
        result = {'stdout': stdout[:16000].decode('utf-8',errors='replace'),
            'stderr': stderr[:16000].decode('utf-8',errors='replace'),
            'exitCode': process.returncode, 'durationMs': int((time.monotonic()-start)*1000),
            'isSimulated': False, 'timedOut': timed_out,
            'outputTruncated': len(stdout)>16000 or len(stderr)>16000}
        if timed_out: result['stderr'] += '\nExecution time limit exceeded.'
        return result

try:
    build = root / 'build'
    build.mkdir(mode=0o700); os.chown(build, student.pw_uid, student.pw_gid)
    compile_result = None
    if language == 'cpp':
        compile_result = run(['g++', '-std=c++17', '-O0', str(source), '-o', str(build / 'program')], '', build, True)
    elif language == 'java':
        compile_result = run(['javac', '-J-Xmx128m', '-J-XX:ActiveProcessorCount=1', '-d', str(build), str(source)], '', build, True)
    results = []
    if compile_result and compile_result['exitCode'] != 0:
        compile_result['compilationFailed'] = True
        results = [compile_result.copy() for _ in request['inputs']]
    else:
        # Make compiled artifacts immutable to submitted programs.
        for path in build.rglob('*'):
            os.chown(path, 0, 0); path.chmod(0o555 if path.is_dir() or path.name=='program' else 0o444)
        os.chown(build, 0, 0); build.chmod(0o555)
        for stdin in request['inputs']:
            with tempfile.TemporaryDirectory(prefix='case-', dir='/tmp') as folder:
                work = Path(folder); os.chown(work, student.pw_uid, student.pw_gid)
                if language == 'python': command = ['python3', '-I', str(source)]
                elif language == 'cpp': command = [str(build / 'program')]
                else: command = ['java', '-Xmx128m', '-Xss512k', '-XX:MaxMetaspaceSize=64m', '-XX:ReservedCodeCacheSize=32m', '-XX:ActiveProcessorCount=1', '-cp', str(build), 'Main']
                results.append(run(command, stdin, work))
    print(json.dumps({'results': results}))
finally:
    shutil.rmtree(root, ignore_errors=True)
`;
