- Backend CI uses standard hosted runners with two test workers in independent
  forks, keeping the full test suite and acceptance gate. The upstream repository
  retains its custom runner and automatic worker count.
