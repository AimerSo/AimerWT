package main

import "strings"

func normalizeBannerColor(raw string) string {
	color := strings.TrimSpace(raw)
	if len(color) != 4 && len(color) != 5 && len(color) != 7 && len(color) != 9 {
		return ""
	}
	if color[0] != '#' {
		return ""
	}
	for _, char := range color[1:] {
		if (char < '0' || char > '9') && (char < 'a' || char > 'f') && (char < 'A' || char > 'F') {
			return ""
		}
	}
	return color
}
