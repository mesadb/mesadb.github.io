/* Copyright (c) 2005, Regents of Massachusetts Institute of Technology, 
 * Brandeis University, Brown University, and University of Massachusetts 
 * Boston. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without 
 * modification, are permitted provided that the following conditions are met:
 *
 *   - Redistributions of source code must retain the above copyright notice, 
 *     this list of conditions and the following disclaimer.
 *   - Redistributions in binary form must reproduce the above copyright 
 *     notice, this list of conditions and the following disclaimer in the 
 *     documentation and/or other materials provided with the distribution.
 *   - Neither the name of Massachusetts Institute of Technology, 
 *     Brandeis University, Brown University, or University of 
 *     Massachusetts Boston nor the names of its contributors may be used 
 *     to endorse or promote products derived from this software without 
 *     specific prior written permission.

 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED 
 * TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR 
 * PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR 
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, 
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, 
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR 
 * PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
 * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS 
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
/**
 * Query 1 Unit Test
 */

#ifndef _QUERY1_H_
#define _QUERY1_H_

#include "../common/Interfaces.h"
#include "../common/Constants.h"
#include "../common/Util.h"

#include "../Wrappers/CodingException.h"
#include "../Wrappers/RLEDataSource.h"
#include "../Wrappers/Decoder/RLEDecoder.h"
#include "../Wrappers/Encoder/RLEEncoder.h"

#include "../Operators/ColumnExtracter.h"
#include "../Operators/Count.h"
#include "../Operators/SlowCount.h"

#include "../AM/AM.h"
#include "../AM/PagePlacer.h"

#include <ctime>
#include "../Paths.h"
#include "../Operators/BlockPrinter.h"
#include "UnitTest.h"

class Query1 : public UnitTest
{
public:
	Query1();
	virtual ~Query1();
	bool run(Globals* g, const vector<string>&);

};

#endif //_QUERY1_H_
