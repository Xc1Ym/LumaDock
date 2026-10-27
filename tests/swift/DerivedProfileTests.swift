import XCTest
@testable import LumaNX

final class DerivedProfileTests: XCTestCase {
    func testSharedContainerContentsHaveDistinctRows() throws {
        let text = """
        {"id":"0100000000010000","name":"Fixture","display":"1.0.1","hidden":false,
         "compatibility":"experimental","missing":[],"preparationMode":"derived","preparationVersion":"v65536",
         "packages":[
          {"titleId":"0100000000010000","baseId":"0100000000010000","type":"base","version":0,"name":"Fixture","display":"1.0.0","path":"shared.xci","size":1,"sha256":"same-container","builds":{}},
          {"titleId":"0100000000010800","baseId":"0100000000010000","type":"update","version":65536,"name":"Fixture","display":"1.0.1","path":"shared.xci","size":1,"sha256":"same-container","builds":{}}
         ]}
        """
        let game=try JSONDecoder().decode(Game.self,from:Data(text.utf8))
        XCTAssertTrue(game.buildable)
        XCTAssertEqual(game.preparationMode,"derived")
        XCTAssertEqual(game.preparationVersion,"v65536")
        XCTAssertEqual(Set(game.packages.map(\.id)).count,2)
    }
}
