/**
 * Netlify Function for Protein Competition Submissions
 *
 * Receives form submissions with multiple sequences and triggers
 * a GitHub repository_dispatch event for private processing.
 *
 * Environment variables (set in Netlify dashboard):
 * - GITHUB_TOKEN: Personal Access Token with 'repo' scope
 * - GITHUB_OWNER: Repository owner (seoklab)
 * - GITHUB_REPO: Repository name (design-test)
 */

const VALID_AMINO_ACIDS = new Set('ACDEFGHIKLMNPQRSTVWY');
const MIN_LENGTH = 10;
const MAX_LENGTH = 5000;
const MAX_SEQUENCES_PER_PROBLEM = 5;

function validateSequence(seq) {
  const cleaned = seq.toUpperCase().replace(/[^A-Z]/g, '');
  const invalid = [...cleaned].filter(c => !VALID_AMINO_ACIDS.has(c));
  return {
    cleaned,
    length: cleaned.length,
    valid: invalid.length === 0 && cleaned.length >= MIN_LENGTH && cleaned.length <= MAX_LENGTH,
    invalidChars: [...new Set(invalid)],
    tooShort: cleaned.length < MIN_LENGTH,
    tooLong: cleaned.length > MAX_LENGTH
  };
}

function validateId(id) {
  return typeof id === 'string' && /^[A-Za-z0-9_-]+$/.test(id) && id.length > 0 && id.length <= 100;
}

function generateSubmissionId(participantId) {
  // Generate a unique submission ID: participant_timestamp_random
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 6);
  // Sanitize and shorten participant ID for the submission ID
  const sanitizedId = participantId.toLowerCase().replace(/[^a-z0-9]/g, '').substring(0, 20);
  return `${sanitizedId}_${timestamp}_${random}`;
}

async function triggerWorkflow(submissionId, participantId, email, sequences) {
  // Trigger a repository_dispatch event to process the submission privately
  const response = await fetch(
    `https://api.github.com/repos/${process.env.GITHUB_OWNER}/${process.env.GITHUB_REPO}/dispatches`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'Protein-Competition-Netlify',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'new_submission',
        client_payload: {
          submission_id: submissionId,
          participant_id: participantId,
          email: email,
          sequences: sequences,
          submitted_at: new Date().toISOString()
        }
      })
    }
  );

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`GitHub API error: ${response.status} - ${error}`);
  }

  // repository_dispatch returns 204 No Content on success
  return { success: true };
}

exports.handler = async (event, context) => {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers, body: '' };
  }

  // Only accept POST
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ success: false, error: 'Method not allowed' })
    };
  }

  try {
    const body = JSON.parse(event.body);
    const { participant_id, email, sequences } = body;

    // Validate participant_id
    if (!validateId(participant_id)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'Invalid participant ID. Use only letters, numbers, underscores, and hyphens.'
        })
      };
    }

    // Validate email
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'Please provide a valid email address.'
        })
      };
    }

    // Validate sequences object
    if (!sequences || typeof sequences !== 'object' || Object.keys(sequences).length === 0) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'No sequences provided.'
        })
      };
    }

    // Validate each problem's sequences (supports array of sequences per problem)
    const validatedSequences = {};
    for (const [problemId, seqData] of Object.entries(sequences)) {
      // Validate problem ID format
      if (!validateId(problemId)) {
        return {
          statusCode: 400,
          headers,
          body: JSON.stringify({
            success: false,
            error: `Invalid problem ID: ${problemId}`
          })
        };
      }

      // Normalize to array (support both single string and array format)
      const seqArray = Array.isArray(seqData) ? seqData : [seqData];

      // Validate sequence count
      if (seqArray.length === 0) {
        return {
          statusCode: 400,
          headers,
          body: JSON.stringify({
            success: false,
            error: `${problemId}: At least one sequence is required.`
          })
        };
      }
      if (seqArray.length > MAX_SEQUENCES_PER_PROBLEM) {
        return {
          statusCode: 400,
          headers,
          body: JSON.stringify({
            success: false,
            error: `${problemId}: Maximum ${MAX_SEQUENCES_PER_PROBLEM} sequences allowed per problem.`
          })
        };
      }

      // Validate each sequence in the array
      const validatedSeqArray = [];
      for (let i = 0; i < seqArray.length; i++) {
        const sequence = seqArray[i];
        const seqResult = validateSequence(sequence || '');
        if (!seqResult.valid) {
          const seqNum = seqArray.length > 1 ? ` (sequence ${i + 1})` : '';
          let errorMsg = `Invalid sequence for ${problemId}${seqNum}.`;
          if (seqResult.invalidChars.length > 0) {
            errorMsg = `${problemId}${seqNum}: Invalid amino acids: ${seqResult.invalidChars.join(', ')}`;
          } else if (seqResult.tooShort) {
            errorMsg = `${problemId}${seqNum}: Sequence too short. Minimum ${MIN_LENGTH} residues required.`;
          } else if (seqResult.tooLong) {
            errorMsg = `${problemId}${seqNum}: Sequence too long. Maximum ${MAX_LENGTH} residues allowed.`;
          }
          return {
            statusCode: 400,
            headers,
            body: JSON.stringify({ success: false, error: errorMsg })
          };
        }
        validatedSeqArray.push(seqResult.cleaned);
      }

      validatedSequences[problemId] = validatedSeqArray;
    }

    // Generate unique submission ID with participant name
    const submissionId = generateSubmissionId(participant_id);

    // Trigger GitHub workflow via repository_dispatch
    await triggerWorkflow(submissionId, participant_id, email, validatedSequences);

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        success: true,
        message: 'Submission received! Your sequences will be processed shortly.',
        submission_id: submissionId,
        problem_count: Object.keys(validatedSequences).length
      })
    };

  } catch (error) {
    console.error('Error processing submission:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        success: false,
        error: 'Failed to process submission. Please try again later.'
      })
    };
  }
};
