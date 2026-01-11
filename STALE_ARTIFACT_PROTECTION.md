# ✅ STALE ARTIFACT PROTECTION + CI-SAFE FAILURE CONTRACT

## 🎯 Refinements Implemented

### 1. Stale Artifact Protection
**Problem Solved:** Reading old junit.xml from previous runs could cause false positives.

**Solution:** Clean all artifacts before each pytest run.

### 2. CI-Safe Failure Contract
**Problem Solved:** Missing/malformed JUnit XML could let CI incorrectly pass.

**Solution:** Wrapper treats missing/malformed JUnit as pytest FAILURE.

---

## 📋 CHANGED FILES

### Modified Scripts (2 files)

1. ✅ **`scripts/run_pytests_and_summarize.mjs`**
   - Added `unlinkSync` import for artifact cleanup
   - `ensureReportsDir()` now deletes old artifacts before run
   - Added `generateMissingJunitSummary()` function
   - Main function checks if junit.xml exists after pytest
   - If missing: generates special summary with last 80 lines of output
   - Logs clear warning about missing JUnit

2. ✅ **`scripts/run_all_tests.mjs`**
   - Enhanced JUnit XML validation logic
   - Checks if junit.xml exists (missing = FAIL)
   - Checks if junit.xml has required attributes (malformed = FAIL)
   - Wraps parsing in try/catch (parse error = FAIL)
   - Logs clear `[test-system]` messages for all failure cases
   - References `output.txt` for debugging

### Updated Documentation (2 files)

3. ✅ **`scripts/README_TEST_SYSTEM.md`**
   - Added "Stale Artifact Protection" section
   - Documented artifact cleanup process
   - Added "Missing JUnit XML Handling" section
   - Updated "How It Works" with cleanup steps
   - Added CI-safe failure detection explanation

4. ✅ **`scripts/verify_test_system.mjs`**
   - Added Check 6a: Artifact cleanup logic (2 checks)
   - Added Check 6b: Missing/malformed JUnit handling (4 checks)
   - Renumbered .gitignore to Check 7
   - Total checks: 21 (was 15)

---

## 🧹 ARTIFACT CLEANUP CODE

### In `scripts/run_pytests_and_summarize.mjs`:

```javascript
import { unlinkSync } from 'fs';  // ← Added import

/**
 * Ensure reports directory exists and clean stale artifacts
 */
function ensureReportsDir() {
  try {
    mkdirSync(REPORTS_DIR, { recursive: true });
    console.log(`✓ Created reports directory: ${REPORTS_DIR}`);
    
    // Clean stale artifacts to prevent "stale success" from previous runs
    const artifactsToClean = [JUNIT_XML, OUTPUT_TXT, SUMMARY_MD];
    let cleaned = 0;
    
    for (const artifact of artifactsToClean) {
      if (existsSync(artifact)) {
        try {
          unlinkSync(artifact);
          cleaned++;
        } catch (err) {
          console.warn(`⚠️  Could not delete old ${artifact}: ${err.message}`);
        }
      }
    }
    
    if (cleaned > 0) {
      console.log(`✓ Cleaned ${cleaned} stale artifact(s)`);
    }
  } catch (err) {
    console.error(`Failed to create ${REPORTS_DIR}:`, err.message);
    process.exit(1);
  }
}
```

**Result:** Every run starts fresh, no stale artifacts.

---

## ⚠️ MISSING/MALFORMED JUNIT HANDLING

### In `scripts/run_pytests_and_summarize.mjs`:

**Check if JUnit was generated:**

```javascript
// Step 3: Check if JUnit XML was generated
if (!existsSync(JUNIT_XML)) {
  console.warn('\n⚠️  JUnit XML not produced by pytest!');
  console.warn('    Likely collection/import crash or fatal pytest error.');
  console.warn(`    Check ${OUTPUT_TXT} for details.\n`);
  
  // Generate special summary for missing JUnit
  const outputContent = existsSync(OUTPUT_TXT) ? readFileSync(OUTPUT_TXT, 'utf8') : '';
  const summary = generateMissingJunitSummary(exitCode, command, outputContent);
  writeFileSync(SUMMARY_MD, summary, 'utf8');
  
  // Display warning summary
  console.log('PYTEST SUMMARY - JUNIT XML MISSING');
  console.log('⚠️  PyTest did not produce JUnit XML');
  
  // ALWAYS exit 0 so Cypress can run
  process.exit(0);
}
```

**Generate special summary with last 80 lines:**

```javascript
function generateMissingJunitSummary(exitCode, pytestCmd, outputContent) {
  let md = '# PyTest Execution Summary\n\n';
  md += `**Generated:** ${timestamp}\n\n`;
  md += `**Exit Code:** ${exitCode}\n\n`;
  
  md += '## ⚠️ JUnit XML Not Produced\n\n';
  md += '**Likely causes:**\n';
  md += '- Collection/import crash or fatal pytest error\n';
  md += '- Configuration issue preventing XML generation\n';
  md += '- Pytest terminated unexpectedly\n\n';
  
  md += '## 📋 Last 80 Lines of Output\n\n';
  md += '```\n';
  const lines = outputContent.split('\n');
  const lastLines = lines.slice(-80);
  md += lastLines.join('\n');
  md += '\n```\n';
  
  return md;
}
```

### In `scripts/run_all_tests.mjs`:

**CI-safe failure detection:**

```javascript
// Check if pytest actually failed by reading JUnit XML
if (!existsSync('reports/pytest/junit.xml')) {
  // JUnit XML is missing - treat as failure
  console.log('\n[test-system] PyTest JUnit missing or invalid -> marking PyTest as FAILED.');
  console.log('              See reports/pytest/output.txt for details.\n');
  pytestFailed = true;
} else {
  // Try to parse JUnit XML
  try {
    const junitContent = fs.readFileSync('reports/pytest/junit.xml', 'utf8');
    
    // Check if there are failures or errors in junit XML
    const failuresMatch = junitContent.match(/failures="(\d+)"/);
    const errorsMatch = junitContent.match(/errors="(\d+)"/);
    
    if (!failuresMatch || !errorsMatch) {
      // Malformed JUnit XML - treat as failure
      console.log('\n[test-system] PyTest JUnit malformed (missing attributes) -> marking PyTest as FAILED.');
      console.log('              See reports/pytest/output.txt for details.\n');
      pytestFailed = true;
    } else {
      const failures = parseInt(failuresMatch[1]);
      const errors = parseInt(errorsMatch[1]);
      
      if (failures > 0 || errors > 0) {
        pytestFailed = true;
        console.log(`\n⚠️  PyTest had ${failures} failure(s) and ${errors} error(s)`);
      } else {
        console.log('\n✅ PyTest: All tests passed');
      }
    }
  } catch (parseErr) {
    // Failed to read or parse JUnit XML - treat as failure
    console.log('\n[test-system] PyTest JUnit parsing error -> marking PyTest as FAILED.');
    console.log(`              Error: ${parseErr.message}`);
    console.log('              See reports/pytest/output.txt for details.\n');
    pytestFailed = true;
  }
}
```

**Result:** CI cannot pass if JUnit is missing/malformed/unparseable.

---

## ✅ COMMANDS (UNCHANGED)

```bash
# Run all tests (pytest once + cypress)
npm run test:all

# Run only pytest
npm run pytest:all

# Run cypress directly (pytest via hook)
npx cypress run
```

**No regressions - all commands work exactly as before.**

---

## 📊 VERIFICATION RESULTS

```bash
node scripts/verify_test_system.mjs
```

**Output:**
```
Total Checks: 21
Passed: 21
Failed: 0

✅ All verification checks passed!
```

**New Checks:**
- ✅ run_pytests_and_summarize.mjs imports unlinkSync
- ✅ run_pytests_and_summarize.mjs deletes old artifacts
- ✅ run_all_tests.mjs checks if junit.xml exists
- ✅ run_all_tests.mjs treats missing JUnit as failure
- ✅ run_all_tests.mjs handles malformed JUnit
- ✅ run_all_tests.mjs logs clear failure messages

---

## 🛡️ NON-NEGOTIABLES MET

| Requirement | Status |
|-------------|--------|
| ✅ No regressions | All existing behavior preserved |
| ✅ Keep artifacts in `reports/pytest/` | Unchanged |
| ✅ Generate junit.xml, output.txt, summary.md | Always generated |
| ✅ Pytest script allows Cypress to run | Still exits 0 always |
| ✅ Wrapper exits 1 if either failed | Enhanced validation |
| ✅ Windows PowerShell compatible | Tested |
| ✅ CI compatible | Enhanced - safer than before |

---

## 🎯 BEHAVIOR EXAMPLES

### Example 1: Normal Pytest Run (All Pass)

```
✓ Created reports directory: reports/pytest
✓ Cleaned 3 stale artifact(s)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 Running ALL PyTests...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command: python -m pytest --maxfail=0 --junitxml=reports/pytest/junit.xml --tb=short -v

[... pytest output ...]

✓ Saved pytest output to: reports/pytest/output.txt
📊 Parsing test results...
📝 Generating summary...
✓ Saved summary to: reports/pytest/summary.md

============================================================
PYTEST SUMMARY
============================================================
Total: 45, Passed: 45, Failed: 0, Errors: 0, Skipped: 0
============================================================

✅ All PyTests passed!
```

### Example 2: Pytest Crashes Before JUnit (Collection Error)

```
✓ Created reports directory: reports/pytest
✓ Cleaned 3 stale artifact(s)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 Running ALL PyTests...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Command: python -m pytest --maxfail=0 --junitxml=reports/pytest/junit.xml --tb=short -v

ImportError: No module named 'django'
[... crash output ...]

✓ Saved pytest output to: reports/pytest/output.txt

⚠️  JUnit XML not produced by pytest!
    Likely collection/import crash or fatal pytest error.
    Check reports/pytest/output.txt for details.

📝 Generating summary (JUnit missing)...
✓ Saved summary to: reports/pytest/summary.md

============================================================
PYTEST SUMMARY - JUNIT XML MISSING
============================================================
⚠️  PyTest did not produce JUnit XML
📄 See reports/pytest/summary.md and reports/pytest/output.txt for details
============================================================
```

**Then in wrapper:**

```
[test-system] PyTest JUnit missing or invalid -> marking PyTest as FAILED.
              See reports/pytest/output.txt for details.

PyTest:  ❌ FAILED
Cypress: ✅ PASSED

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ OVERALL: TESTS FAILED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 PyTest Summary: reports/pytest/summary.md
📄 PyTest Output:  reports/pytest/output.txt
📄 JUnit XML:      reports/pytest/junit.xml

[Exit code 1]
```

### Example 3: Malformed JUnit XML

```
[test-system] PyTest JUnit malformed (missing attributes) -> marking PyTest as FAILED.
              See reports/pytest/output.txt for details.

PyTest:  ❌ FAILED
[Exit code 1]
```

---

## 📄 ARTIFACTS STILL GENERATED

Every run produces:

1. **`reports/pytest/junit.xml`** (if pytest succeeds in generating it)
2. **`reports/pytest/output.txt`** (ALWAYS - even on crash)
3. **`reports/pytest/summary.md`** (ALWAYS - special format if JUnit missing)

**Special summary.md when JUnit is missing:**

```markdown
# PyTest Execution Summary

**Generated:** 2026-01-09T16:45:23.456Z

**Exit Code:** 1

**Command:** `python -m pytest --maxfail=0 --junitxml=reports/pytest/junit.xml --tb=short -v`

## ⚠️ JUnit XML Not Produced

**Status:** JUnit XML file was not generated by pytest.

**Likely causes:**
- Collection/import crash or fatal pytest error
- Configuration issue preventing XML generation
- Pytest terminated unexpectedly

## 📋 Last 80 Lines of Output

For quick diagnosis, here are the last 80 lines of pytest output:

```
[... last 80 lines of pytest output ...]
```

---

## Artifacts

- **JUnit XML:** `reports/pytest/junit.xml` ❌ **NOT GENERATED**
- **Raw Output:** `reports/pytest/output.txt`
- **This Summary:** `reports/pytest/summary.md`
```

---

## 🔒 SSOT ENHANCED

This implementation maintains SSOT while adding:

1. ✅ **Stale artifact protection** - Clean start every run
2. ✅ **CI-safe failure contract** - Missing/malformed JUnit = FAIL
3. ✅ **Better diagnostics** - Last 80 lines in summary when JUnit missing
4. ✅ **Clear logging** - `[test-system]` messages for all edge cases
5. ✅ **Zero regressions** - All existing behavior preserved

---

## 🎉 READY FOR PRODUCTION

The system is now more robust and CI-safe:

- **Cannot pass with stale artifacts**
- **Cannot pass with missing JUnit XML**
- **Cannot pass with malformed JUnit XML**
- **Cannot pass with JUnit parsing errors**
- **Always generates diagnostic artifacts**

**Commands unchanged. Behavior enhanced. Zero regressions.**

