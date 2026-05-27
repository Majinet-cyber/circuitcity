#!/usr/bin/env node

/**
 * run_pytests_and_summarize.mjs
 * 
 * Runs ALL PyTests and generates:
 * - reports/pytest/junit.xml (JUnit format)
 * - reports/pytest/output.txt (raw console output)
 * - reports/pytest/summary.md (human-readable failure summary)
 * 
 * ALWAYS exits with code 0 (even if pytest fails) so Cypress can still run.
 * The wrapper script (run_all_tests.mjs) will handle overall exit code.
 */

import { execSync } from 'child_process';
import { mkdirSync, writeFileSync, readFileSync, existsSync, unlinkSync, renameSync } from 'fs';
import { dirname } from 'path';
import { fileURLToPath } from 'url';
import crypto from 'crypto';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Paths
const REPORTS_DIR = 'reports/pytest';
const JUNIT_XML = `${REPORTS_DIR}/junit.xml`;
const OUTPUT_TXT = `${REPORTS_DIR}/output.txt`;
const SUMMARY_MD = `${REPORTS_DIR}/summary.md`;

/**
 * Generate unique run ID for traceability
 */
function generateRunId() {
  const timestamp = new Date().toISOString().replace(/[-:T.Z]/g, '').slice(0, 14);
  const randomSuffix = crypto.randomBytes(3).toString('hex');
  return `${timestamp}-${randomSuffix}`;
}

/**
 * Atomic write - write to temp file then rename to avoid partial writes
 */
function atomicWrite(filePath, content) {
  const tmpPath = `${filePath}.tmp`;
  try {
    writeFileSync(tmpPath, content, 'utf8');
    renameSync(tmpPath, filePath);
  } catch (err) {
    // Clean up temp file if rename failed
    try {
      if (existsSync(tmpPath)) {
        unlinkSync(tmpPath);
      }
    } catch {}
    throw err;
  }
}

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

/**
 * Run pytest with junit output and capture console output
 * Returns { exitCode, output, command }
 */
function runPytest() {
  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('🧪 Running ALL PyTests...');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

  // Pytest command - Explicitly run ALL tests without early stopping
  // --maxfail=0: Never stop early, run all tests regardless of failures
  // --junitxml: Produce JUnit XML for CI integration
  // --tb=short: Shorter traceback format
  // -v: Verbose output
  const pytestCmd = `python -m pytest --maxfail=0 --junitxml=${JUNIT_XML} --tb=short -v`;
  
  console.log(`Command: ${pytestCmd}\n`);
  
  let output = '';
  let exitCode = 0;

  try {
    output = execSync(pytestCmd, {
      encoding: 'utf8',
      stdio: 'pipe',
      windowsHide: true,
      shell: true,
    });
    console.log(output);
    exitCode = 0;
  } catch (err) {
    // pytest returns non-zero if tests fail
    output = err.stdout || '';
    if (err.stderr) {
      output += '\n--- STDERR ---\n' + err.stderr;
    }
    console.log(output);
    exitCode = err.status || 1;
    console.log(`\n⚠️  PyTest exited with code ${exitCode}`);
  }

  // Always write output to file (atomic write to avoid partial files)
  try {
    atomicWrite(OUTPUT_TXT, output);
    console.log(`✓ Saved pytest output to: ${OUTPUT_TXT}`);
  } catch (err) {
    console.error(`Failed to write ${OUTPUT_TXT}:`, err.message);
  }

  return { exitCode, output, command: pytestCmd };
}

/**
 * Parse JUnit XML and extract test results
 */
function parseJunitXml() {
  if (!existsSync(JUNIT_XML)) {
    return {
      total: 0,
      failures: 0,
      errors: 0,
      skipped: 0,
      testCases: [],
    };
  }

  try {
    const xmlContent = readFileSync(JUNIT_XML, 'utf8');
    
    // Simple XML parsing (no dependencies)
    const testsuiteMatch = xmlContent.match(/<testsuite[^>]*>/);
    let total = 0, failures = 0, errors = 0, skipped = 0;
    
    if (testsuiteMatch) {
      const attrs = testsuiteMatch[0];
      total = parseInt(attrs.match(/tests="(\d+)"/)?.[1] || '0');
      failures = parseInt(attrs.match(/failures="(\d+)"/)?.[1] || '0');
      errors = parseInt(attrs.match(/errors="(\d+)"/)?.[1] || '0');
      skipped = parseInt(attrs.match(/skipped="(\d+)"/)?.[1] || '0');
    }

    // Extract failed test cases
    const testCases = [];
    const testcaseRegex = /<testcase[^>]*>(.*?)<\/testcase>/gs;
    let match;

    while ((match = testcaseRegex.exec(xmlContent)) !== null) {
      const testcaseTag = match[0];
      const testcaseContent = match[1];
      
      // Only process if it has failure or error
      if (testcaseContent.includes('<failure') || testcaseContent.includes('<error')) {
        const classname = testcaseTag.match(/classname="([^"]*)"/)?.[1] || 'unknown';
        const name = testcaseTag.match(/name="([^"]*)"/)?.[1] || 'unknown';
        const file = testcaseTag.match(/file="([^"]*)"/)?.[1] || '';
        
        let message = '';
        let type = 'unknown';
        
        // Try to extract failure message
        const failureMatch = testcaseContent.match(/<failure[^>]*message="([^"]*)"[^>]*>(.*?)<\/failure>/s);
        if (failureMatch) {
          type = 'failure';
          message = failureMatch[1] || failureMatch[2] || '';
        }
        
        // Try to extract error message
        const errorMatch = testcaseContent.match(/<error[^>]*message="([^"]*)"[^>]*>(.*?)<\/error>/s);
        if (errorMatch) {
          type = 'error';
          message = errorMatch[1] || errorMatch[2] || '';
        }
        
        // Decode XML entities
        message = message
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&amp;/g, '&')
          .replace(/&quot;/g, '"')
          .replace(/&#x27;/g, "'");
        
        testCases.push({
          classname,
          name,
          file,
          type,
          message: message.trim(),
        });
      }
    }

    return { total, failures, errors, skipped, testCases };
  } catch (err) {
    console.error(`Failed to parse ${JUNIT_XML}:`, err.message);
    return {
      total: 0,
      failures: 0,
      errors: 0,
      skipped: 0,
      testCases: [],
    };
  }
}

/**
 * Categorize error based on message heuristics
 */
function categorizeError(message) {
  const lower = message.toLowerCase();
  
  if (lower.includes('noreversmatch')) return 'NoReverseMatch';
  if (lower.includes('templatesyntaxerror')) return 'TemplateSyntaxError';
  if (lower.includes('nameerror')) return 'NameError';
  if (lower.includes('assertionerror') || lower.includes('assert ')) return 'AssertionError';
  if (lower.includes('attributeerror')) return 'AttributeError';
  if (lower.includes('keyerror')) return 'KeyError';
  if (lower.includes('typeerror')) return 'TypeError';
  if (lower.includes('valueerror')) return 'ValueError';
  if (lower.includes('importerror') || lower.includes('modulenotfounderror')) return 'ImportError';
  if (lower.includes('indentationerror')) return 'IndentationError';
  if (lower.includes('syntaxerror')) return 'SyntaxError';
  if (lower.includes('permission') || lower.includes('403')) return 'PermissionError';
  if (lower.includes('404') || lower.includes('not found')) return 'NotFound';
  if (lower.includes('500') || lower.includes('internal server')) return 'ServerError';
  
  return 'Other';
}

/**
 * Truncate message to first N lines
 */
function truncateMessage(message, maxLines = 30) {
  const lines = message.split('\n');
  if (lines.length <= maxLines) {
    return message;
  }
  return lines.slice(0, maxLines).join('\n') + `\n... (${lines.length - maxLines} more lines)`;
}

/**
 * Generate markdown summary for missing JUnit XML
 */
function generateMissingJunitSummary(exitCode, pytestCmd, outputContent, runId) {
  const timestamp = new Date().toISOString();
  const isWrapperRun = process.env.CC_SKIP_PYTEST !== '1';  // If not skipping, running via hook
  const envMarker = isWrapperRun ? 'hook' : 'wrapper';
  
  let md = '';
  md += '# PyTest Execution Summary\n\n';
  md += `**Run ID:** ${runId}\n\n`;
  md += `**Generated:** ${timestamp}\n\n`;
  md += `**Exit Code:** ${exitCode}\n\n`;
  md += `**Environment:** ${envMarker}\n\n`;
  if (pytestCmd) {
    md += `**Command:** \`${pytestCmd}\`\n\n`;
  }
  
  md += '## ⚠️ JUnit XML Not Produced\n\n';
  md += '**Status:** JUnit XML file was not generated by pytest.\n\n';
  md += '**Likely causes:**\n';
  md += '- Collection/import crash or fatal pytest error\n';
  md += '- Configuration issue preventing XML generation\n';
  md += '- Pytest terminated unexpectedly\n\n';
  
  md += '## 📋 Last 80 Lines of Output\n\n';
  md += 'For quick diagnosis, here are the last 80 lines of pytest output:\n\n';
  md += '```\n';
  
  if (outputContent) {
    const lines = outputContent.split('\n');
    const lastLines = lines.slice(-80);
    md += lastLines.join('\n');
  } else {
    md += '(No output available)';
  }
  
  md += '\n```\n\n';
  
  md += '---\n\n';
  md += '## Artifacts\n\n';
  md += `- **JUnit XML:** \`${JUNIT_XML}\` ❌ **NOT GENERATED**\n`;
  md += `- **Raw Output:** \`${OUTPUT_TXT}\`\n`;
  md += `- **This Summary:** \`${SUMMARY_MD}\`\n\n`;
  md += '---\n\n';
  md += '*This summary was auto-generated by `run_pytests_and_summarize.mjs`*\n';
  
  return md;
}

/**
 * Generate markdown summary
 */
function generateSummary(results, exitCode, pytestCmd = '', runId = '') {
  const timestamp = new Date().toISOString();
  const passed = results.total - results.failures - results.errors - results.skipped;
  const isWrapperRun = process.env.CC_SKIP_PYTEST !== '1';
  const envMarker = isWrapperRun ? 'hook' : 'wrapper';
  
  let md = '';
  md += '# PyTest Execution Summary\n\n';
  md += `**Run ID:** ${runId}\n\n`;
  md += `**Generated:** ${timestamp}\n\n`;
  md += `**Exit Code:** ${exitCode}\n\n`;
  md += `**Environment:** ${envMarker}\n\n`;
  if (pytestCmd) {
    md += `**Command:** \`${pytestCmd}\`\n\n`;
  }
  md += '## Test Results\n\n';
  md += `- **Total Tests:** ${results.total}\n`;
  md += `- **Passed:** ${passed}\n`;
  md += `- **Failed:** ${results.failures}\n`;
  md += `- **Errors:** ${results.errors}\n`;
  md += `- **Skipped:** ${results.skipped}\n\n`;
  
  if (exitCode === 0) {
    md += '## ✅ All Tests Passed!\n\n';
    md += 'No failures to report.\n\n';
  } else {
    md += '## ❌ Test Failures\n\n';
    
    if (results.testCases.length === 0) {
      md += '*No detailed failure information available. Check `output.txt` for raw pytest output.*\n\n';
    } else {
      // Group by error category
      const grouped = {};
      results.testCases.forEach(tc => {
        const category = categorizeError(tc.message);
        if (!grouped[category]) {
          grouped[category] = [];
        }
        grouped[category].push(tc);
      });
      
      md += `**Total Failures/Errors:** ${results.testCases.length}\n\n`;
      
      // Summary by category
      md += '### Failure Categories\n\n';
      for (const [category, cases] of Object.entries(grouped)) {
        md += `- **${category}:** ${cases.length}\n`;
      }
      md += '\n---\n\n';
      
      // Detailed failures
      md += '### Detailed Failures\n\n';
      
      for (const [category, cases] of Object.entries(grouped)) {
        md += `#### ${category} (${cases.length})\n\n`;
        
        cases.forEach((tc, idx) => {
          md += `##### ${idx + 1}. \`${tc.classname}.${tc.name}\`\n\n`;
          if (tc.file) {
            md += `**File:** \`${tc.file}\`\n\n`;
          }
          md += `**Type:** ${tc.type}\n\n`;
          md += '**Error Message:**\n\n';
          md += '```\n';
          md += truncateMessage(tc.message, 30);
          md += '\n```\n\n';
        });
      }
    }
  }
  
  md += '---\n\n';
  md += '## Artifacts\n\n';
  md += `- **JUnit XML:** \`${JUNIT_XML}\`\n`;
  md += `- **Raw Output:** \`${OUTPUT_TXT}\`\n`;
  md += `- **This Summary:** \`${SUMMARY_MD}\`\n\n`;
  md += '---\n\n';
  md += '*This summary was auto-generated by `run_pytests_and_summarize.mjs`*\n';
  
  return md;
}

/**
 * Main execution
 */
function main() {
  // Generate unique run ID for this test execution
  const runId = generateRunId();
  console.log(`[Run ID: ${runId}]`);
  
  try {
    // Step 1: Ensure reports directory and clean stale artifacts
    ensureReportsDir();
    
    // Step 2: Run pytest
    const { exitCode, output, command } = runPytest();
    
    // Step 3: Check if JUnit XML was generated
    if (!existsSync(JUNIT_XML)) {
      console.warn('\n⚠️  JUnit XML not produced by pytest!');
      console.warn('    Likely collection/import crash or fatal pytest error.');
      console.warn(`    Check ${OUTPUT_TXT} for details.\n`);
      
      // Generate special summary for missing JUnit
      console.log('📝 Generating summary (JUnit missing)...');
      const outputContent = existsSync(OUTPUT_TXT) ? readFileSync(OUTPUT_TXT, 'utf8') : '';
      const summary = generateMissingJunitSummary(exitCode, command, outputContent, runId);
      atomicWrite(SUMMARY_MD, summary);
      console.log(`✓ Saved summary to: ${SUMMARY_MD}`);
      
      console.log('\n' + '='.repeat(60));
      console.log('PYTEST SUMMARY - JUNIT XML MISSING');
      console.log('='.repeat(60));
      console.log('⚠️  PyTest did not produce JUnit XML');
      console.log(`📄 See ${SUMMARY_MD} and ${OUTPUT_TXT} for details`);
      console.log('='.repeat(60));
      
      // ALWAYS exit 0 so Cypress can run
      process.exit(0);
    }
    
    // Step 4: Parse junit XML (normal path)
    console.log('\n📊 Parsing test results...');
    const results = parseJunitXml();
    
    // Step 5: Generate summary
    console.log('📝 Generating summary...');
    const summary = generateSummary(results, exitCode, command, runId);
    atomicWrite(SUMMARY_MD, summary);
    console.log(`✓ Saved summary to: ${SUMMARY_MD}`);
    
    // Step 6: Display summary
    console.log('\n' + '='.repeat(60));
    console.log('PYTEST SUMMARY');
    console.log('='.repeat(60));
    console.log(`Total: ${results.total}, Passed: ${results.total - results.failures - results.errors - results.skipped}, Failed: ${results.failures}, Errors: ${results.errors}, Skipped: ${results.skipped}`);
    console.log('='.repeat(60));
    
    if (exitCode !== 0) {
      console.log('\n⚠️  PyTest had failures, but continuing to Cypress...');
      console.log(`📄 See ${SUMMARY_MD} for details\n`);
    } else {
      console.log('\n✅ All PyTests passed!\n');
    }
    
    // ALWAYS exit 0 so Cypress can run
    process.exit(0);
    
  } catch (err) {
    console.error('\n❌ Fatal error in run_pytests_and_summarize.mjs:', err.message);
    console.error(err.stack);
    
    // Even on fatal error, try to write a minimal summary
    try {
      const errorSummary = `# PyTest Execution Summary\n\n**ERROR:** Script failed\n\n\`\`\`\n${err.message}\n\`\`\`\n`;
      atomicWrite(SUMMARY_MD, errorSummary);
    } catch {}
    
    // Exit 0 to allow Cypress to run
    process.exit(0);
  }
}

main();

