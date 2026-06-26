package main

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"
	"golang.org/x/text/encoding/simplifiedchinese"
	"golang.org/x/text/transform"
)

var (
	buildVersion = "dev"
	buildTime    = "unknown"
)

func main() {
	versionFlag := flag.Bool("version", false, "Show version")
	host := flag.String("host", "", "Device IP address (required)")
	port := flag.Int("port", 22, "SSH port")
	username := flag.String("user", "", "SSH username (required)")
	password := flag.String("pass", "", "SSH password")
	encryptedPassword := flag.String("enc-pass", "", "Encrypted SSH password")
	key := flag.String("key", "", "Encryption key (32 bytes for AES-256)")
	commands := flag.String("cmd", "", "Commands to execute (comma-separated)")
	commandFile := flag.String("cmd-file", "", "File containing commands (one per line)")
	encoding := flag.String("encoding", "UTF-8", "Output encoding (UTF-8 or GBK)")
	timeout := flag.Int("timeout", 30, "Timeout in seconds")
	enablePass := flag.String("enable-pass", "", "Enable password (for devices needing privilege mode)")
	enable := flag.Bool("enable", false, "Send enable command to enter privilege mode")
	encryptMode := flag.String("encrypt", "", "Encrypt text and exit")
	flag.Parse()

	if *encryptMode != "" {
		keyBytes := []byte(*key)
		if len(keyBytes) != 32 {
			fmt.Fprintf(os.Stderr, "Encryption key must be 32 bytes for AES-256\n")
			os.Exit(1)
		}
		encrypted, err := encrypt(*encryptMode, keyBytes)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Encryption failed: %v\n", err)
			os.Exit(1)
		}
		fmt.Println(encrypted)
		os.Exit(0)
	}

	if *versionFlag {
		fmt.Fprintf(os.Stderr, "netagent_linux version=%s build=%s\n", buildVersion, buildTime)
		os.Exit(0)
	}

	if *host == "" || *username == "" {
		fmt.Println("Usage:")
		flag.PrintDefaults()
		os.Exit(1)
	}

	var cmdList []string
	if *commands != "" {
		for _, cmd := range bytes.Split([]byte(*commands), []byte(",")) {
			cmdList = append(cmdList, string(cmd))
		}
	} else if *commandFile != "" {
		data, err := os.ReadFile(*commandFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to read command file: %v\n", err)
			os.Exit(1)
		}
		for _, line := range bytes.Split(data, []byte("\n")) {
			lineStr := string(bytes.TrimSpace(line))
			if lineStr != "" && lineStr[0] != '#' {
				cmdList = append(cmdList, lineStr)
			}
		}
	} else {
		fmt.Fprintf(os.Stderr, "Either --cmd or --cmd-file must be provided\n")
		os.Exit(1)
	}

	var pwd string
	if *encryptedPassword != "" {
		if *key == "" {
			fmt.Fprintf(os.Stderr, "Encryption key (-key) is required when using encrypted password\n")
			os.Exit(1)
		}
		decrypted, err := decrypt(*encryptedPassword, []byte(*key))
		if err != nil {
			fmt.Fprintf(os.Stderr, "Failed to decrypt password: %v\n", err)
			os.Exit(1)
		}
		pwd = decrypted
	} else if *password != "" {
		pwd = *password
	} else {
		fmt.Fprintf(os.Stderr, "Either --pass or --enc-pass must be provided\n")
		os.Exit(1)
	}

	results, err := executeSSH(*host, *port, *username, pwd, *enablePass, *enable, cmdList, *encoding, *timeout)
	if err != nil {
		msg := err.Error()
		if isAuthError(msg) {
			fmt.Fprintf(os.Stderr, "[ERROR] SSH authentication failed for %s@%s - 用户名或密码错误，请检查凭据\n", *username, *host)
			fmt.Fprintf(os.Stderr, "[ERROR] Detail: %v\n", err)
		} else {
			fmt.Fprintf(os.Stderr, "[ERROR] SSH execution failed: %v\n", err)
		}
		os.Exit(1)
	}

	for _, result := range results {
		fmt.Printf("=== Command: %s ===\n", result.Command)
		fmt.Println(result.Output)
		if result.Error != "" {
			fmt.Printf("[ERROR] %s\n", result.Error)
		}
		fmt.Println("=== End ===")
	}
}

type result struct {
	Command string
	Output  string
	Error   string
}

func isAuthError(msg string) bool {
	lower := strings.ToLower(msg)
	if strings.Contains(lower, "unable to authenticate") ||
		strings.Contains(lower, "authentication failed") ||
		strings.Contains(lower, "no supported methods remain") ||
		strings.Contains(lower, "could not authenticate") {
		return true
	}
	return false
}

func executeSSH(host string, port int, username string, password string, enablePass string, enable bool, commands []string, encoding string, timeout int) ([]result, error) {
	sshConfig := &ssh.ClientConfig{
		User: username,
		Auth: []ssh.AuthMethod{
			ssh.Password(password),
		},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         time.Duration(timeout) * time.Second,
		Config: ssh.Config{
			KeyExchanges: []string{
				"curve25519-sha256",
				"curve25519-sha256@libssh.org",
				"ecdh-sha2-nistp256",
				"ecdh-sha2-nistp384",
				"ecdh-sha2-nistp521",
				"diffie-hellman-group14-sha256",
				"diffie-hellman-group14-sha1",
				"diffie-hellman-group-exchange-sha256",
				"diffie-hellman-group-exchange-sha1",
				"diffie-hellman-group1-sha1",
			},
			Ciphers: []string{
				"aes128-gcm@openssh.com",
				"aes256-gcm@openssh.com",
				"chacha20-poly1305@openssh.com",
				"aes128-ctr",
				"aes192-ctr",
				"aes256-ctr",
				"aes128-cbc",
				"aes192-cbc",
				"aes256-cbc",
				"3des-cbc",
			},
		},
	}

	addr := fmt.Sprintf("%s:%d", host, port)
	fmt.Fprintf(os.Stderr, "[DEBUG] Dialing %s ...\n", addr)
	client, err := ssh.Dial("tcp", addr, sshConfig)
	if err != nil {
		errMsg := err.Error()
		if isAuthError(errMsg) {
			return nil, fmt.Errorf("SSH authentication failed for %s@%s - 用户名或密码错误 (detail: %v)", username, host, err)
		}
		return nil, fmt.Errorf("failed to connect to %s:%d: %v", host, port, err)
	}
	defer client.Close()
	fmt.Fprintf(os.Stderr, "[DEBUG] Connected\n")

	session, err := client.NewSession()
	if err != nil {
		return nil, fmt.Errorf("failed to create session: %v", err)
	}
	defer session.Close()
	// fmt.Fprintf(os.Stderr, "[DEBUG] Session created\n")

	modes := ssh.TerminalModes{
		ssh.ECHO:          1,
		ssh.TTY_OP_ISPEED: 14400,
		ssh.TTY_OP_OSPEED: 14400,
	}
	// if err := session.RequestPty("vt100", 80, 24, modes); err != nil {
	// 	fmt.Fprintf(os.Stderr, "[DEBUG] PTY request failed: %v\n", err)
	// }
	session.RequestPty("vt100", 80, 24, modes)

	var buf bytes.Buffer
	session.Stdout = &buf
	session.Stderr = &buf

	stdin, err := session.StdinPipe()
	if err != nil {
		return nil, fmt.Errorf("failed to get stdin pipe: %v", err)
	}

	// fmt.Fprintf(os.Stderr, "[DEBUG] Starting shell...\n")
	if err := session.Shell(); err != nil {
		return nil, fmt.Errorf("failed to start shell: %v", err)
	}

	// 等待初始输出收集设备 banner 和登录提示，最长 10 秒
	loginOutput := ""
	hasPasswordPrompt := false
	authFailureFound := ""
	for i := 0; i < 20; i++ {
		time.Sleep(500 * time.Millisecond)
		loginOutput = buf.String()
		lowerOutput := strings.ToLower(loginOutput)
		hasPasswordPrompt = strings.Contains(lowerOutput, "password:") || strings.Contains(lowerOutput, "password：") ||
			strings.Contains(lowerOutput, "'s password")
		authFailureFound = hasAuthFailure(loginOutput)
		if hasPasswordPrompt || authFailureFound != "" {
			break
		}
		// 正常登录成功 → 检测到真正的 shell 提示符即可退出等待
		if extractPrompt(loginOutput) != ">" {
			break
		}
	}

	// 10 秒后如果没有任何设备输出 → 连接有问题
	if buf.Len() == 0 && !hasPasswordPrompt && authFailureFound == "" {
		return nil, fmt.Errorf("no output received from %s:%d in 10 seconds after shell start - device may be unresponsive or authentication failed", host, port)
	}

	// password 提示或认证失败 → 立即报错返回，不再发命令
	if hasPasswordPrompt || authFailureFound != "" {
		fmt.Fprintf(os.Stderr, "[ERROR] SSH auth detected during login\n")
		for _, l := range strings.Split(loginOutput, "\n") {
			l = strings.TrimRight(l, "\r ")
			if l != "" {
				fmt.Fprintf(os.Stderr, "[LOGIN] %s\n", l)
			}
		}
		reason := "unknown"
		if hasPasswordPrompt {
			reason = "device requested password (password incorrect or keyboard-interactive auth needed)"
		} else if authFailureFound != "" {
			reason = authFailureFound
		}
		return nil, fmt.Errorf("SSH authentication failed for %s@%s - %s (device says: %s)", username, host, reason, strings.ReplaceAll(strings.TrimSpace(loginOutput), "\r", ""))
	}

	// 检测密码过期交互提示，自动应答 N
	if strings.Contains(loginOutput, "password is already expired") ||
		strings.Contains(loginOutput, "Change now?") {
		fmt.Fprintf(os.Stderr, "[LOGIN] Warning: The password is already expired\n")
		stdin.Write([]byte("N\r\n"))
		time.Sleep(2 * time.Second)
		loginOutput = buf.String()
		// 应答 N 后检测是否被设备断开
		responseClean := strings.ReplaceAll(strings.TrimSpace(loginOutput), "\r", "")
		if responseClean != "" {
			fmt.Fprintf(os.Stderr, "[LOGIN] %s\n", responseClean)
		}
		if strings.Contains(loginOutput, "denied") || strings.Contains(loginOutput, "refused") ||
			loginOutput == "" {
			fmt.Fprintf(os.Stderr, "[ERROR] 密码已过期，设备拒绝登录（连接已断开），请联系网络管理员更新密码\n")
			return nil, fmt.Errorf("password expired - device rejected login for %s@%s", username, host)
		}
	}

	// 登录输出文本前 10 行（用于识别设备类型）
	currentOutput := buf.String()
	loginLines := strings.Split(currentOutput, "\n")
	headerLines := loginLines
	if len(headerLines) > 10 {
		headerLines = headerLines[:10]
	}
	for _, l := range headerLines {
		l = strings.TrimRight(l, "\r ")
		if l != "" {
			fmt.Fprintf(os.Stderr, "[LOGIN] %s\n", l)
		}
	}

	prompt := extractPrompt(currentOutput)
	fmt.Fprintf(os.Stderr, "[LOGIN] Detected prompt: '%s'\n", prompt)

	// ---- Enable 提权 ----
	if enable {
		fmt.Fprintf(os.Stderr, "[ENABLE] Sending enable command...\n")
		beforeLen := buf.Len()
		stdin.Write([]byte("enable\n"))

		enableStart := time.Now()
		enableTimeout := 10 * time.Second
		passwordSent := false
		enableSuccess := false

		for time.Since(enableStart) < enableTimeout {
			time.Sleep(200 * time.Millisecond)

			currentOutput := buf.String()
			newSinceCmd := currentOutput[beforeLen:]
			lowerNew := strings.ToLower(newSinceCmd)

			// Detect password prompt and send password
			if !passwordSent && (strings.Contains(lowerNew, "password:") || strings.Contains(lowerNew, "password：")) {
				if enablePass == "" {
					fmt.Fprintf(os.Stderr, "[ENABLE] Device requests enable password but none provided, sending empty line and continuing\n")
					stdin.Write([]byte("\n"))
					passwordSent = true
					continue
				}
				fmt.Fprintf(os.Stderr, "[ENABLE] Sending enable password...\n")
				stdin.Write([]byte(enablePass + "\n"))
				passwordSent = true
				continue
			}

			// Check if prompt changed (no longer ends with >)
			candidate := extractPrompt(currentOutput)
			if !strings.HasSuffix(candidate, ">") && candidate != prompt {
				fmt.Fprintf(os.Stderr, "[ENABLE] Prompt changed: '%s'\n", candidate)
				prompt = candidate
				enableSuccess = true
				break
			}

			// Log waiting status every 2 seconds
			elapsed := time.Since(enableStart).Seconds()
			if elapsed >= 2 && int(elapsed)%2 == 0 {
				fmt.Fprintf(os.Stderr, "[ENABLE] Waiting for enable to complete, %.0fs elapsed\n", elapsed)
			}
		}

		if !enableSuccess {
			finalPrompt := extractPrompt(buf.String())
			fmt.Fprintf(os.Stderr, "[ENABLE] Enable timeout (%s), extracted prompt: '%s'\n", time.Since(enableStart).Round(time.Second), finalPrompt)
			prompt = finalPrompt
		}
	}
	// ---- Enable 提权结束 ----

	fmt.Fprintf(os.Stderr, "[AWAKE] Wake before commands...\n")
	stdin.Write([]byte("\r\n"))
	time.Sleep(2 * time.Second)
	fmt.Fprintf(os.Stderr, "[AWAKE] Wake done.\n")

	results := make([]result, 0, len(commands))

	prevLen := buf.Len()

	for _, cmd := range commands {
		startTime := time.Now()

		// 发命令前先检查缓冲区中是否有认证失败信息（用严格模式）
		currentBuf := buf.String()[prevLen:]
		if failLine := hasAuthFailureStrict(currentBuf); failLine != "" {
			fmt.Fprintf(os.Stderr, "[ERROR] Device returned auth error: %s, aborting\n", failLine)
			results = append(results, result{
				Command: cmd,
				Error:   fmt.Sprintf("device auth error: %s", failLine),
			})
			continue
		}

		cmdStart := buf.Len()
		stdin.Write([]byte(cmd + "\r\n"))
		fmt.Fprintf(os.Stderr, "[DEBUG] Sent: %s\n", cmd)

		promptFound := waitForPrompt(&buf, stdin, prompt, buf.Len(), time.Duration(timeout)*time.Second)
		if !promptFound {
			// waitForPrompt 可能因检测到认证失败而提前返回 false
			afterOutput := buf.String()[cmdStart:]
			if failLine := hasAuthFailureStrict(afterOutput); failLine != "" {
				// 输出设备返回的完整认证失败信息
				for _, l := range strings.Split(afterOutput, "\n") {
					l = strings.TrimRight(l, "\r ")
					if l != "" {
						fmt.Fprintf(os.Stderr, "[LOGIN] %s\n", l)
					}
				}
				return nil, fmt.Errorf("device rejected login: %s", strings.ReplaceAll(strings.TrimSpace(afterOutput), "\r", ""))
			}
			fmt.Fprintf(os.Stderr, "[DEBUG] Timeout waiting for prompt after command: %s\n", cmd)
		}

		elapsed := time.Since(startTime)

		fmt.Fprintf(os.Stderr, "[EXEC_TIME] %s: %.2fs\n", cmd, elapsed.Seconds())

		output := buf.String()[cmdStart:]

		if encoding == "GBK" {
			output = convertGBKToUTF8(output)
		}

		output = cleanOutputSimple(output, cmd, prompt)

		results = append(results, result{Command: cmd, Output: output})

		prevLen = buf.Len()
	}

	stdin.Write([]byte("exit\r\n"))

	// 命令已执行完毕，只需等 session 正常退出即可，最多等 5 秒
	done := make(chan error, 1)
	go func() {
		done <- session.Wait()
	}()
	select {
	case err := <-done:
		if err != nil {
			fmt.Fprintf(os.Stderr, "[DEBUG] Session wait error: %v\n", err)
		}
	case <-time.After(2 * time.Second):
		fmt.Fprintf(os.Stderr, "[DEBUG] Session wait timeout (2s)\n")
	}

	return results, nil
}

func extractPrompt(output string) string {
	clean := stripANSI(output)
	// Remove null bytes (H3C RBM devices may embed \x00 before prompt)
	clean = strings.ReplaceAll(clean, "\x00", "")
	lines := strings.Split(clean, "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if len(line) > 0 && (strings.HasSuffix(line, ">") || strings.HasSuffix(line, "#") || strings.HasSuffix(line, "$")) {
			return line
		}
	}
	return ">"
}

var ansiRegexp = regexp.MustCompile(`\x1b\[[0-9;]*[a-zA-Z]`)

func stripANSI(input string) string {
	return ansiRegexp.ReplaceAllString(input, "")
}

// hasAuthFailure 检测输出中是否包含设备返回的认证失败信息或密码输入提示
func hasAuthFailure(output string) string {
	lower := strings.ToLower(output)
	if !strings.Contains(lower, "password") && !strings.Contains(lower, "authentication") &&
		!strings.Contains(lower, "permission") && !strings.Contains(lower, "login") &&
		!strings.Contains(lower, "denied") && !strings.Contains(lower, "refused") {
		return ""
	}
	lines := strings.Split(output, "\n")
	for _, line := range lines {
		lineTrim := strings.TrimSpace(line)
		lowerLine := strings.ToLower(lineTrim)
		// 检测密码输入提示
		if strings.HasSuffix(lowerLine, "password:") || strings.HasSuffix(lowerLine, "password：") ||
			strings.Contains(lowerLine, "'s password") {
			return lineTrim
		}
		// 检测明确的认证失败信息
		if strings.Contains(lowerLine, "authentication failed") ||
			strings.Contains(lowerLine, "authentication failure") ||
			strings.Contains(lowerLine, "permission denied") ||
			strings.Contains(lowerLine, "login incorrect") ||
			strings.Contains(lowerLine, "password incorrect") ||
			strings.Contains(lowerLine, "access denied") ||
			strings.Contains(lowerLine, "not allowed") {
			return lineTrim
		}
	}
	return ""
}

// hasAuthFailureStrict 用于命令执行期间 waitForPrompt 内部的检测
// 只检测最明确的认证失败信号，避免设备配置内容误触发
func hasAuthFailureStrict(output string) string {
	lines := strings.Split(output, "\n")
	for _, line := range lines {
		lineTrim := strings.TrimSpace(line)
		lowerLine := strings.ToLower(lineTrim)
		// 只检测密码输入提示和明确的认证失败
		// 注意："authentication failed/failure" 必须是独立单词（前面有空格/行首），
		// 避免匹配到配置内容如 "lock-authentication failed-count 5"
		if strings.HasSuffix(lowerLine, "password:") || strings.HasSuffix(lowerLine, "password：") ||
			strings.Contains(lowerLine, "'s password") ||
			strings.Contains(lowerLine, "login incorrect") ||
			strings.Contains(lowerLine, "password incorrect") {
			return lineTrim
		}
		for _, phrase := range []string{"authentication failed", "authentication failure"} {
			// 只匹配行首，避免配置内容（如 "security authentication failure rate 3"）误命中
			if strings.HasPrefix(lowerLine, phrase) {
				return lineTrim
			}
		}
	}
	return ""
}

func waitForPrompt(buf *bytes.Buffer, stdin io.Writer, prompt string, startFrom int, timeout time.Duration) bool {
	startTime := time.Now()
	pos := startFrom
	lastHeartbeat := startTime
	fmt.Fprintf(os.Stderr, "[DBG_WFP] prompt=%q timeout=%.0fs startFrom=%d\n", prompt, timeout.Seconds(), startFrom)

	for time.Since(startTime) < timeout {
		output := buf.String()
		if len(output) <= pos {
			time.Sleep(100 * time.Millisecond)
			if time.Since(lastHeartbeat) >= 2*time.Second {
			currentBufLen := buf.Len()
			elapsed := time.Since(startTime).Seconds()
			// Show last 300 bytes of buffer for debugging
			tail := output
			if len(tail) > 300 { tail = tail[len(tail)-300:] }
			cleanTail := stripANSI(strings.ReplaceAll(tail, "\r", ""))
			fmt.Fprintf(os.Stderr, "[DBG] %.0fs bufLen=%d content=%q\n", elapsed, currentBufLen, cleanTail)
			lastHeartbeat = time.Now()
		}
			continue
		}
		newOutput := output[pos:]
		rawOutput := strings.ReplaceAll(newOutput, "\r", "")
		cleanOutput := stripANSI(rawOutput)
		lines := strings.Split(cleanOutput, "\n")

		// 检测 ---- More ----（Cisco）或 --More--（Fortinet/H3C等）并发送空格翻页
		moreFound := false
		for _, line := range lines {
			if strings.Contains(line, "---- More ----") || strings.Contains(line, "--More--") || strings.Contains(line, "<--- More --->") || strings.Contains(line, "---(more)---") || strings.Contains(line, "---(more)---") || strings.Contains(line, "---(more)---") || strings.Contains(line, "---(more)---") {
				pos = buf.Len()
				stdin.Write([]byte(" "))
				time.Sleep(10 * time.Millisecond)
				moreFound = true
				break
			}
		}
		if moreFound {
			continue
		}

		// 检测设备是否返回认证失败信息（用严格模式，避免配置内容如"Access Denied"误触发）
		for _, line := range lines {
			failLine := strings.TrimSpace(line)
			if failLine != "" && hasAuthFailureStrict(failLine) != "" {
				fmt.Fprintf(os.Stderr, "[ERROR] Device returned auth error: %s\n", failLine)
				return false
			}
		}

		// 检测提示符
		promptFound := false
		for i := len(lines) - 1; i >= 0; i-- {
			line := strings.TrimSpace(lines[i])
			if line != "" {
				if len(prompt) <= 1 {
					if line == prompt {
						promptFound = true
					}
				} else {
					if line == prompt || strings.HasSuffix(line, prompt) {
						promptFound = true
					}
				}
				break
			}
		}

		if promptFound {
			// 找到提示符后等 200ms 让设备数据收全
			time.Sleep(200 * time.Millisecond)
			outputNow := buf.String()
			if len(outputNow) > len(output) {
				// 有新数据到达，但重新验证提示符是否仍在末尾
				// 如果在，说明只是零星回显/控制字符，直接返回
				rest := outputNow[pos:]
				cleanRest := stripANSI(strings.ReplaceAll(rest, "\r", ""))
				restLines := strings.Split(cleanRest, "\n")
				for i := len(restLines) - 1; i >= 0; i-- {
					trimmed := strings.TrimSpace(restLines[i])
					if trimmed != "" {
						if (len(prompt) <= 1 && trimmed == prompt) ||
							(len(prompt) > 1 && (trimmed == prompt || strings.HasSuffix(trimmed, prompt))) {
							return true // 提示符仍在末尾，输出已完整
						}
						break
					}
				}
				continue
			}
			return true
		}

		time.Sleep(50 * time.Millisecond)
	}
	// 超时前检查新输出中是否含有 password: 等认证提示
	postOutput := buf.String()[pos:]
	postLower := strings.ToLower(postOutput)
	if strings.Contains(postLower, "password:") || strings.Contains(postLower, "password：") ||
		strings.Contains(postLower, "'s password") ||
		strings.Contains(postLower, "authentication failed") {
		fmt.Fprintf(os.Stderr, "[WAIT_PROMPT] Detected auth prompt in device output, aborting\n")
		return false
	}
	// 超时前尝试发 \r 唤醒设备（部分USG防火墙需要）
	fmt.Fprintf(os.Stderr, "[WAIT_PROMPT] timeout, sending wake to device...\n")
	stdin.Write([]byte("\r\n"))
	wakeDeadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(wakeDeadline) {
		output := buf.String()
		if len(output) > pos {
			newOutput := output[pos:]
			rawOutput := strings.ReplaceAll(newOutput, "\r", "")
			cleanOutput := stripANSI(rawOutput)
			lines := strings.Split(cleanOutput, "\n")
			for i := len(lines) - 1; i >= 0; i-- {
				line := strings.TrimSpace(lines[i])
				if line != "" {
					if len(prompt) <= 1 {
						if line == prompt {
							fmt.Fprintf(os.Stderr, "[WAIT_PROMPT] Device woken by \\r, prompt found: '%s'\n", line)
							return true
						}
					} else {
						if line == prompt || strings.HasSuffix(line, prompt) {
							fmt.Fprintf(os.Stderr, "[WAIT_PROMPT] Device woken by \\r, prompt found: '%s'\n", line)
							return true
						}
					}
					break
				}
			}
		}
		time.Sleep(100 * time.Millisecond)
	}

	// 超时前最后一次检查设备新输出（方便调试）
	newOutput := buf.String()[pos:]
	if len(newOutput) > 0 {
		cleanPart := strings.ReplaceAll(newOutput, "\r", "")
		cleanPart = stripANSI(cleanPart)
		newLines := strings.Split(cleanPart, "\n")
		nonEmpty := []string{}
		for _, l := range newLines {
			if strings.TrimSpace(l) != "" {
				nonEmpty = append(nonEmpty, strings.TrimSpace(l))
			}
		}
		if len(nonEmpty) > 0 {
			start := 0
			if len(nonEmpty) > 5 {
				start = len(nonEmpty) - 5
			}
			for _, l := range nonEmpty[start:] {
				fmt.Fprintf(os.Stderr, "[DEVICE] %s\n", l)
			}
		}
	}

	// 超时后返回 false
	return false
}

func cleanOutputSimple(output, cmd, prompt string) string {
	// 处理退格符 \b：移除 \b 及其前面的字符
	for strings.ContainsRune(output, '\b') {
		idx := strings.IndexRune(output, '\b')
		if idx > 0 {
			output = output[:idx-1] + output[idx+1:]
		} else {
			output = output[idx+1:]
		}
	}

	output = strings.ReplaceAll(output, "\r\n", "\n")
	output = strings.ReplaceAll(output, "\r", "\n")
	output = stripANSI(output)

	lines := strings.Split(output, "\n")

	// 找到最后一个提示符位置（而非第一个），
	// 避免 Juniper cluster 回显中出现的提示符提前截断输出
	lastPromptIdx := -1
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == prompt || strings.HasSuffix(trimmed, prompt) {
			lastPromptIdx = i
		}
	}

	result := make([]string, 0)
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)

		if len(result) == 0 {
			if trimmed == "" || strings.HasPrefix(trimmed, "*") ||
				strings.HasPrefix(trimmed, "Info:") ||
				strings.HasPrefix(trimmed, "The max") ||
				strings.HasPrefix(trimmed, "The current") {
				continue
			}
			result = append(result, trimmed)
			continue
		}

		// 过滤分页标记 (<--- More --->, ---- More ----, --More--)
		if strings.Contains(trimmed, "<--- More --->") || strings.Contains(trimmed, "---(more)---") ||
			strings.Contains(trimmed, "---- More ----") ||
			strings.Contains(trimmed, "--More--") {
			continue
		}

		if i == lastPromptIdx {
			result = append(result, trimmed)
			break
		}

		if trimmed != "" {
			result = append(result, trimmed)
		}
	}

	return strings.Join(result, "\n")
}

func convertGBKToUTF8(input string) string {
	reader := transform.NewReader(bytes.NewReader([]byte(input)), simplifiedchinese.GBK.NewDecoder())
	result, err := io.ReadAll(reader)
	if err != nil {
		return input
	}
	return string(result)
}

func encrypt(text string, key []byte) (string, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}

	ciphertext := gcm.Seal(nonce, nonce, []byte(text), nil)
	return base64.URLEncoding.EncodeToString(ciphertext), nil
}

func decrypt(ciphertext string, key []byte) (string, error) {
	data, err := base64.URLEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}

	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}

	nonceSize := gcm.NonceSize()
	if len(data) < nonceSize {
		return "", fmt.Errorf("invalid ciphertext")
	}

	nonce, ciphertextBytes := data[:nonceSize], data[nonceSize:]
	plaintext, err := gcm.Open(nil, nonce, ciphertextBytes, nil)
	if err != nil {
		return "", err
	}

	return string(plaintext), nil
}
