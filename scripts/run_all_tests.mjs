#!/usr/bin/env node

/**
 * run_all_tests.mjs
 * 
 * Wrapper script that:
 * 1. Runs ALL PyTests (via run_pytests_and_summarize.mjs)
 * 2. Runs Cypress tests
 * 3. Exits with code 1 if EITHER pytest or cypress failed
 * 
 * This is the SSOT for running all tests locally and in CI.
 * 
 * Usage:
 *   npm run test:all
 *   OR
 *   node scripts/run_all_tests.mjs
 */

import { execSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { XMLParser } from 'fast-xml-parser';

console.log('\n╔══════════════════════════════════════════════════════════════╗');
console.log('║                   RUNNING ALL TESTS                          ║');
console.log('╚══════════════════════════════════════════════════════════════╝\n');

let pytestFailed = false;
let cypressFailed = false;

// ============================================================================
// Step 1: Run PyTests
// ============================================================================
console.log('📍 Step 1/2: Running PyTests...\n');

try {
  execSync('node scripts/run_pytests_and_summarize.mjs', {
    stdio: 'inherit',
    shell: true,
  });
  
  // Check if pytest actually failed by reading JUnit XML
  // The script always exits 0, so we need to check the artifacts
  if (!existsSync('reports/pytest/junit.xml')) {
    // JUnit XML is missing - treat as failure
    console.log('\n[test-system] PyTest JUnit missing or invalid -> marking PyTest as FAILED.');
    console.log('              See reports/pytest/output.txt for details.\n');
    pytestFailed = true;
  } else {
    // Try to parse JUnit XML with proper XML parser
    try {
      const junitContent = readFileSync('reports/pytest/junit.xml', 'utf8');
      
      // Parse XML using fast-xml-parser
      const parser = new XMLParser({
        ignoreAttributes: false,
        attributeNamePrefix: '@_',
      });
      const result = parser.parse(junitContent);
      
      // Support both single testsuite and testsuites wrapper
      let totalFailures = 0;
      let totalErrors = 0;
      
      if (result.testsuites) {
        // Multiple test suites wrapped in <testsuites>
        const suites = Array.isArray(result.testsuites.testsuite) 
          ? result.testsuites.testsuite 
          : [result.testsuites.testsuite];
        
        for (const suite of suites) {
          if (suite) {
            totalFailures += parseInt(suite['@_failures'] || '0');
            totalErrors += parseInt(suite['@_errors'] || '0');
          }
        }
      } else if (result.testsuite) {
        // Single testsuite at root level
        totalFailures = parseInt(result.testsuite['@_failures'] || '0');
        totalErrors = parseInt(result.testsuite['@_errors'] || '0');
      } else {
        // Unexpected structure
        throw new Error('JUnit XML has unexpected structure (no testsuite or testsuites)');
      }
      
      if (totalFailures > 0 || totalErrors > 0) {
        pytestFailed = true;
        console.log(`\n⚠️  PyTest had ${totalFailures} failure(s) and ${totalErrors} error(s)`);
      } else {
        console.log('\n✅ PyTest: All tests passed');
      }
      
    } catch (parseErr) {
      // Failed to parse JUnit XML - treat as failure
      console.log('\n[test-system] PyTest JUnit XML parsing error -> marking PyTest as FAILED.');
      console.log(`              Parse error: ${parseErr.message}`);
      
      // Fall back to scanning output.txt for conservative failure indicators
      try {
        if (existsSync('reports/pytest/output.txt')) {
          const output = readFileSync('reports/pytest/output.txt', 'utf8');
          const failureIndicators = ['FAILED', 'ERROR', '== FAILURES ==', '== ERRORS =='];
          const hasFailures = failureIndicators.some(indicator => 
            output.toUpperCase().includes(indicator)
          );
          
          if (hasFailures) {
            console.log('              Fallback: detected failure indicators in output.txt');
          } else {
            console.log('              Fallback: no clear failure indicators, but marking as FAILED (fail-closed)');
          }
        }
      } catch (fallbackErr) {
        console.log('              Fallback scan also failed, marking as FAILED (fail-closed)');
      }
      
      console.log('              See reports/pytest/output.txt for details.\n');
      pytestFailed = true;
    }
  }
} catch (err) {
  console.error('\n❌ Failed to run PyTests:', err.message);
  pytestFailed = true;
}

console.log('\n' + '─'.repeat(70) + '\n');

// ============================================================================
// Step 2: Run Cypress
// ============================================================================
console.log('📍 Step 2/2: Running Cypress tests...\n');

try {
  // Set CC_SKIP_PYTEST=1 to prevent Cypress hook from running pytest again
  execSync('npx cypress run', {
    stdio: 'inherit',
    shell: true,
    env: {
      ...process.env,
      CC_SKIP_PYTEST: '1',
    },
  });
  console.log('\n✅ Cypress: All tests passed');
} catch (err) {
  console.error('\n❌ Cypress tests failed');
  cypressFailed = true;
}

// ============================================================================
// Final Summary
// ============================================================================
console.log('\n╔══════════════════════════════════════════════════════════════╗');
console.log('║                    FINAL TEST SUMMARY                        ║');
console.log('╚══════════════════════════════════════════════════════════════╝\n');

console.log(`PyTest:  ${pytestFailed ? '❌ FAILED' : '✅ PASSED'}`);
console.log(`Cypress: ${cypressFailed ? '❌ FAILED' : '✅ PASSED'}`);

if (pytestFailed || cypressFailed) {
  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('❌ OVERALL: TESTS FAILED');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
  
  if (pytestFailed) {
    console.log('📄 PyTest Summary: reports/pytest/summary.md');
    console.log('📄 PyTest Output:  reports/pytest/output.txt');
    console.log('📄 JUnit XML:      reports/pytest/junit.xml\n');
  }
  
  process.exit(1);
} else {
  console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('✅ OVERALL: ALL TESTS PASSED');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');
  process.exit(0);
}

