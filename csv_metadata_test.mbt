///|
test "renamed quoted metadata survives record and event-window CSV export" {
  let fast : @edf.Signal = {
    label: "before",
    transducer: "",
    unit: "u,\"V\"",
    physical_min: 0.0,
    physical_max: 2.0,
    digital_min: 0,
    digital_max: 2,
    prefilter: "",
    samples_per_record: 3,
    reserved: "",
  }
  let source = @edf.create(
    [fast, { ..fast, label: "slow", unit: "uV", samples_per_record: 2, }],
    [
      {
        onset: "0",
        samples: [[0, 1, 2], [1, 2]],
        events: [{ onset: "0.1", duration: Some("0.4"), text: "mark", }],
      },
    ],
    "0.6",
  )
  let before = source.encode()
  let renamed = source.rename_signal(0, "A,\"B\",\"C\"")
  let matches = renamed.find_annotations("0.1", "0.5")
  assert_eq(matches.length(), 1)
  assert_eq(matches[0].annotation.text, "mark")
  let epoch = renamed.event_window(
    matches[0].annotation_index,
    [0, 1],
    before="0",
    after="0",
    max_samples=3,
  )
  assert_true(epoch.complete)
  assert_eq(epoch.samples, 3)
  assert_eq(epoch.channels[0].label, "A,\"B\",\"C\"")
  assert_eq(epoch.channels[0].unit, "u,\"V\"")
  let record_csv =
    #|signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit
    #|0,"A,""B"",""C""",0,0,0,0,1,0,"u,""V"""
    #|0,"A,""B"",""C""",0,1,0.2,1,5,1,"u,""V"""
    #|0,"A,""B"",""C""",0,2,0.4,2,5,2,"u,""V"""
    #|1,"slow",0,0,0,0,1,1,"uV"
    #|1,"slow",0,1,0.3,3,10,2,"uV"
    #|
  assert_eq(renamed.csv([0, 1]), record_csv)
  let window_csv =
    #|signal,label,record,sample,time_seconds,time_numerator,time_denominator,value,unit
    #|0,"A,""B"",""C""",0,1,0.2,1,5,1,"u,""V"""
    #|0,"A,""B"",""C""",0,2,0.4,2,5,2,"u,""V"""
    #|1,"slow",0,1,0.3,3,10,2,"uV"
    #|
  assert_eq(
    renamed.window_csv([0, 1], epoch.start, epoch.end, max_samples=3),
    window_csv,
  )
  assert_eq(source.encode(), before)
}
