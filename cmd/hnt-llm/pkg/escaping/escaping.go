package escaping

import (
	"bytes"
	"io"
	"regexp"
	"strings"
)

var (
	escapeRegex   = regexp.MustCompile(`<(/?)(_*)(hnt-(user|assistant|system))>`)
	unescapeRegex = regexp.MustCompile(`<(/?)(_+)(hnt-(user|assistant|system))>`)
)

func Escape(reader io.Reader, writer io.Writer) error {
	content, err := io.ReadAll(reader)
	if err != nil {
		return err
	}

	result := escapeRegex.ReplaceAllFunc(content, func(match []byte) []byte {
		matches := escapeRegex.FindSubmatch(match)
		if len(matches) < 4 {
			return match
		}

		slash := matches[1]
		underscores := matches[2]
		hntRole := matches[3]

		var buf bytes.Buffer
		buf.WriteByte('<')
		buf.Write(slash)
		buf.Write(underscores)
		buf.WriteByte('_')
		buf.Write(hntRole)
		buf.WriteByte('>')
		return buf.Bytes()
	})

	_, err = writer.Write(result)
	return err
}

func Unescape(input string) string {
	return unescapeRegex.ReplaceAllStringFunc(input, func(match string) string {
		matches := unescapeRegex.FindStringSubmatch(match)
		if len(matches) < 4 {
			return match
		}

		slash := matches[1]
		underscores := matches[2]
		hntRole := matches[3]

		newUnderscores := ""
		if len(underscores) > 0 {
			newUnderscores = underscores[1:]
		}

		return "<" + slash + newUnderscores + hntRole + ">"
	})
}

func EscapeString(input string) string {
	var buf bytes.Buffer
	err := Escape(strings.NewReader(input), &buf)
	if err != nil {
		return input
	}
	return buf.String()
}
