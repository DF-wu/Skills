package speaker

import (
	"sort"
	"strings"
)

// ResolveResult describes how a speaker name was resolved.
type ResolveResult struct {
	Resolved string // exact Gradio dropdown string; "" if no match
	Kind     string // "default", "alias", "exact", "case-insensitive", "prefix", "substring", ""
}

// ResolveSpeakerDetailed resolves a user-supplied speaker name to the exact
// Gradio dropdown string and reports HOW it was matched. Use this when you
// want to warn the user about fuzzy matches.
func ResolveSpeakerDetailed(name string) ResolveResult {
	if name == "" {
		return ResolveResult{Resolved: DefaultSpeaker, Kind: "default"}
	}
	lower := strings.ToLower(name)

	// 1. Exact match in upstream choices wins. Critical for names like
	//    "派蒙" / "琴" / "刻晴" which exist verbatim as CN voices AND as alias
	//    keys pointing to a JP voice. The user typed it exactly — honor it.
	for _, gc := range UpstreamChoices {
		if gc == name {
			return ResolveResult{Resolved: gc, Kind: "exact"}
		}
	}
	// 2. Case-insensitive exact
	for _, gc := range UpstreamChoices {
		if strings.ToLower(gc) == lower {
			return ResolveResult{Resolved: gc, Kind: "case-insensitive"}
		}
	}
	// 3. Exact alias (e.g. "ayaka", or "甘雨" which has no upstream-exact variant)
	if target, ok := SpeakerAliases[name]; ok {
		return ResolveResult{Resolved: target, Kind: "alias"}
	}
	// 4. Case-insensitive alias
	for alias, target := range SpeakerAliases {
		if strings.ToLower(alias) == lower {
			return ResolveResult{Resolved: target, Kind: "alias"}
		}
	}
	// 5. Prefix match (requires ≥2 chars)
	if len(name) >= 2 {
		for _, gc := range UpstreamChoices {
			if strings.HasPrefix(gc, name) {
				return ResolveResult{Resolved: gc, Kind: "prefix"}
			}
		}
	}
	// 6. Substring match (last resort; deterministic via slice order)
	for _, gc := range UpstreamChoices {
		if strings.Contains(gc, name) {
			return ResolveResult{Resolved: gc, Kind: "substring"}
		}
	}
	return ResolveResult{Resolved: "", Kind: ""}
}

// ResolveSpeaker is the legacy string-only resolver kept for callers that
// don't care how the match happened.
func ResolveSpeaker(name string) string {
	return ResolveSpeakerDetailed(name).Resolved
}

func ResolveLanguage(key string) string {
	if key == "" {
		return Languages[DefaultLanguage]
	}
	if v, ok := Languages[key]; ok {
		return v
	}
	lower := strings.ToLower(key)
	for k, v := range Languages {
		if strings.ToLower(k) == lower {
			return v
		}
	}
	// Allow passing the Gradio value directly (中文 / 日语 / mix)
	return key
}

func ListSpeakers() []string {
	sorted := make([]string, len(UpstreamChoices))
	copy(sorted, UpstreamChoices)
	sort.Strings(sorted)
	return sorted
}

// SearchSpeakers returns Gradio strings whose own value OR any alias key
// contains the (case-insensitive) query. Sorted alphabetically.
func SearchSpeakers(query string) []string {
	lower := strings.ToLower(query)
	seen := make(map[string]struct{})
	var out []string
	for _, gc := range UpstreamChoices {
		if strings.Contains(strings.ToLower(gc), lower) {
			if _, ok := seen[gc]; !ok {
				seen[gc] = struct{}{}
				out = append(out, gc)
			}
		}
	}
	for alias, target := range SpeakerAliases {
		if strings.Contains(strings.ToLower(alias), lower) {
			if _, ok := seen[target]; !ok {
				seen[target] = struct{}{}
				out = append(out, target)
			}
		}
	}
	sort.Strings(out)
	return out
}
